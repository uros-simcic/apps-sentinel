"""Classify owner replies; this is not the complete execution gate."""

from typing import Literal

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
