import re

from config import validate
from approval import check_approval
from state import load_state, save_state, upgrade_state


def claim_execution(api, config, state_issue, number, revision):
    approved = check_approval(
        api, config, state_issue, number, revision
    )
    state = upgrade_state(load_state(api, config, state_issue))
    comment_id = approved["comment_id"]
    if any(
        row["comment_id"] == comment_id
        for row in state["executions"]
    ):
        raise ValueError("Approval has already been consumed")

    state["executions"].append({
        "proposal_issue": number,
        "revision": approved["proposal"]["revision"],
        "comment_id": comment_id,
        "status": "claimed",
    })
    save_state(api, config, state_issue, state)
    return approved


def finish_execution(
    api, config, state_issue, number, revision, comment_id, status
):
    validate(config)
    if config["mode"] != "active":
        raise ValueError("Execution updates require active mode")
    if (
        type(number) is not int or number <= 0
        or type(comment_id) is not int or comment_id <= 0
        or not isinstance(revision, str)
        or not re.fullmatch(r"[0-9a-f]{64}", revision)
        or status not in ("succeeded", "failed", "uncertain")
    ):
        raise ValueError("Invalid execution outcome")

    state = upgrade_state(load_state(api, config, state_issue))
    receipt = next(
        (
            row for row in state["executions"]
            if row["comment_id"] == comment_id
        ),
        None,
    )
    if (
        receipt is None
        or receipt["proposal_issue"] != number
        or receipt["revision"] != revision
    ):
        raise ValueError("Execution outcome does not match its claim")
    if receipt["status"] == status:
        return
    if receipt["status"] != "claimed":
        raise ValueError("Execution outcome is already final")

    receipt["status"] = status
    save_state(api, config, state_issue, state)
