"""Classify owner replies; this is not the complete execution gate."""

from datetime import datetime, timezone
from typing import Literal
from urllib.parse import quote

from config import validate
from proposal_store import load_proposal

ReplyKind = Literal["approve", "reject", "feedback"]
MAX_REPLY_CHARS = 4000


def classify_reply(
    body: str,
    actor_id: int,
    owner_id: int,
) -> ReplyKind | None:
    """Ignore invalid/non-owner input; recognize exact decision words only."""
    if type(actor_id) is not int or type(owner_id) is not int:
        return None
    if owner_id <= 0 or actor_id != owner_id:
        return None
    if not isinstance(body, str) or len(body) > MAX_REPLY_CHARS:
        return None

    text = body.strip()
    if not text:
        return None
    if text.casefold() == "approve":
        return "approve"
    if text.casefold() == "reject":
        return "reject"
    return "feedback"


def read_replies(api, config, state_issue, number, revision):
    proposal = load_proposal(api, config, state_issue, number, revision)
    comments = api.pages(
        f"/repos/{config['control_repo']}/issues/{number}/comments"
        "?per_page=100"
    )
    if not isinstance(comments, list):
        raise ValueError("Invalid proposal comment listing")

    replies = []
    seen = set()
    for comment in comments:
        if not isinstance(comment, dict):
            raise ValueError("Malformed proposal comment")
        actor = comment.get("user")
        if not isinstance(actor, dict) or type(actor.get("id")) is not int:
            raise ValueError("Invalid comment author")
        if actor["id"] != config["owner_id"]:
            continue

        comment_id = comment.get("id")
        if type(comment_id) is not int or comment_id <= 0 or comment_id in seen:
            raise ValueError("Invalid or duplicate comment ID")
        seen.add(comment_id)
        kind = classify_reply(
            comment.get("body"), actor["id"], config["owner_id"]
        )
        if kind is None:
            raise ValueError("Owner reply cannot be processed")

        try:
            created = datetime.fromisoformat(
                comment["created_at"].replace("Z", "+00:00")
            )
            updated = datetime.fromisoformat(
                comment["updated_at"].replace("Z", "+00:00")
            )
            if (
                created.utcoffset() is None
                or updated.utcoffset() is None
                or updated < created
            ):
                raise ValueError("Invalid comment timestamps")
        except (KeyError, TypeError, AttributeError, ValueError):
            raise ValueError("Invalid comment timestamps") from None

        edited = updated != created
        replies.append({
            "id": comment_id,
            "kind": "feedback" if edited else kind,
            "body": comment["body"],
            "created_at": created.astimezone(timezone.utc).isoformat(),
            "updated_at": updated.astimezone(timezone.utc).isoformat(),
            "edited": edited,
        })

    replies.sort(key=lambda reply: (reply["updated_at"], reply["id"]))
    return {"proposal": proposal, "replies": replies}


def check_approval(api, config, state_issue, number, revision):
    validate(config)
    if config["mode"] != "active":
        raise ValueError("Execution approval requires active mode")

    review = read_replies(api, config, state_issue, number, revision)
    replies = review["replies"]
    if not replies:
        raise ValueError("Current owner approval required")
    latest = max(
        replies, key=lambda reply: (reply["updated_at"], reply["id"])
    )
    if latest["kind"] != "approve" or latest["edited"]:
        raise ValueError("Current owner approval required")

    proposal = review["proposal"]
    scope = proposal.get("scope")
    if scope is None:
        raise ValueError("Explicit test scope required for execution approval")
    target = "/repos/" + proposal["repo"]
    repo = api.get(target)
    branch = repo.get("default_branch") if isinstance(repo, dict) else None
    if not isinstance(branch, str) or not branch:
        raise ValueError("Missing target default branch")
    if branch != scope["base_branch"]:
        raise ValueError("Approved proposal base branch is no longer current")
    head = api.get(target + "/commits/" + quote(branch, safe=""))
    if not isinstance(head, dict) or head.get("sha") != proposal["base_sha"]:
        raise ValueError("Approved proposal base is no longer current")

    refreshed = read_replies(api, config, state_issue, number, revision)
    if refreshed != review:
        raise ValueError("Proposal or owner replies changed during review")
    return {"proposal": proposal, "comment_id": latest["id"]}
