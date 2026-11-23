import json
import re

from config import validate_identity
from github_client import MAX_ISSUE_BODY_BYTES


class StateError(ValueError):
    pass


def _owner(value, config):
    return (
        isinstance(value, dict)
        and type(value.get("id")) is int
        and value["id"] == config["owner_id"]
        and isinstance(value.get("login"), str)
        and value["login"].casefold() == config["owner_login"].casefold()
    )


def _issue(api, config, number):
    validate_identity(config)
    if type(number) is not int or number <= 0:
        raise StateError("Invalid state issue number")
    if not _owner(api.get("/user"), config):
        raise StateError("State credential does not match owner")

    base = "/repos/" + config["control_repo"]
    repo = api.get(base)
    if (
        not isinstance(repo, dict)
        or repo.get("private") is not True
        or not _owner(repo.get("owner"), config)
        or not isinstance(repo.get("full_name"), str)
        or repo["full_name"].casefold() != config["control_repo"].casefold()
    ):
        raise StateError("State repository must be private and owner-controlled")

    path = f"{base}/issues/{number}"
    issue = api.get(path)
    if (
        not isinstance(issue, dict)
        or type(issue.get("number")) is not int
        or issue["number"] != number
        or "pull_request" in issue
        or issue.get("state") != "open"
        or not _owner(issue.get("user"), config)
    ):
        raise StateError("Invalid owner-controlled state issue")
    return path, issue


def _validate(state):
    if not isinstance(state, dict):
        raise StateError("Invalid state document")
    version = state.get("schema_version")
    expected = {"schema_version", "checks"}
    if version in (2, 3):
        expected.add("executions")
    if version == 3:
        expected.add("outbox")
    if (
        type(version) is not int
        or version not in (1, 2, 3)
        or set(state) != expected
        or not isinstance(state["checks"], list)
    ):
        raise StateError("Invalid state document")

    seen = set()
    for row in state["checks"]:
        if (
            not isinstance(row, dict)
            or set(row) != {"status", "incident_id"}
            or row["status"] not in ("fail", "unknown")
            or not isinstance(row["incident_id"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", row["incident_id"])
            or row["incident_id"] in seen
        ):
            raise StateError("Invalid or duplicate state incident")
        seen.add(row["incident_id"])
    if version in (2, 3):
        _validate_executions(state["executions"])
    if version == 3:
        _validate_outbox(state["outbox"])
    return state


def _validate_executions(receipts):
    if not isinstance(receipts, list):
        raise StateError("Invalid execution receipts")
    seen = set()
    for row in receipts:
        if (
            not isinstance(row, dict)
            or set(row) != {
                "proposal_issue", "revision", "comment_id", "status"
            }
            or type(row["proposal_issue"]) is not int
            or row["proposal_issue"] <= 0
            or type(row["comment_id"]) is not int
            or row["comment_id"] <= 0
            or row["comment_id"] in seen
            or not isinstance(row["revision"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", row["revision"])
            or row["status"] not in (
                "claimed", "succeeded", "failed", "uncertain"
            )
        ):
            raise StateError("Invalid or duplicate execution receipt")
        seen.add(row["comment_id"])


def _validate_outbox(rows):
    if not isinstance(rows, list) or len(rows) > 100:
        raise StateError("Invalid or oversized outbox")
    seen = set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != {
                "proposal_issue", "revision", "status", "attempts"
            }
            or type(row["proposal_issue"]) is not int
            or row["proposal_issue"] <= 0
            or not isinstance(row["revision"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", row["revision"])
            or row["status"] not in (
                "pending", "sending", "sent", "uncertain"
            )
            or type(row["attempts"]) is not int
            or not 0 <= row["attempts"] <= 2
            or (row["status"] != "pending" and row["attempts"] == 0)
        ):
            raise StateError("Invalid outbox entry")
        key = (row["proposal_issue"], row["revision"])
        if key in seen:
            raise StateError("Duplicate outbox entry")
        seen.add(key)


def upgrade_state(state):
    _validate(state)
    result = {
        "schema_version": 3 if state["schema_version"] == 3 else 2,
        "checks": [dict(row) for row in state["checks"]],
        "executions": [
            dict(row) for row in state.get("executions", [])
        ],
    }
    if state["schema_version"] == 3:
        result["outbox"] = [dict(row) for row in state["outbox"]]
    return result


def upgrade_outbox(state):
    result = upgrade_state(state)
    result["schema_version"] = 3
    result.setdefault("outbox", [])
    return result


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise StateError("Duplicate state key")
        result[key] = value
    return result


def _decode(body):
    if (
        not isinstance(body, str)
        or len(body.encode("utf-8")) > MAX_ISSUE_BODY_BYTES
    ):
        raise StateError("Invalid state body")
    try:
        state = json.loads(body, object_pairs_hook=_object)
    except (ValueError, RecursionError):
        raise StateError("Invalid state JSON") from None
    return _validate(state)


def load_state(api, config, number):
    _, issue = _issue(api, config, number)
    return _decode(issue.get("body"))


def save_state(api, config, number, state, *, expected):
    body = json.dumps(_validate(state), sort_keys=True)
    if len(body.encode("utf-8")) > MAX_ISSUE_BODY_BYTES:
        raise StateError("State exceeds size limit")

    path, issue = _issue(api, config, number)
    if _decode(issue.get("body")) != expected:
        raise StateError("State changed since it was read")
    saved = api.update_issue_body(path, body)
    if (
        not isinstance(saved, dict)
        or type(saved.get("number")) is not int
        or saved["number"] != number
        or saved.get("body") != body
    ):
        raise StateError("GitHub did not confirm the intended state")
