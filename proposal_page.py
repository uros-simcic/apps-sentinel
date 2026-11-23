import json
import re

from github_client import MAX_ISSUE_BODY_BYTES
from proposals import validate_proposal


def _block(text, language):
    longest = max(
        (len(run) for run in re.findall(r"`+", text)),
        default=0,
    )
    fence = "`" * max(3, longest + 1)
    return f"{fence}{language}\n{text}\n{fence}"


def format_test_scope(scope):
    return (
        "Operation: Run approved tests only\n"
        f"Base branch: {scope['base_branch']}\n"
        f"Test profile: {scope['test_profile']}\n"
        f"Test profile SHA-256: {scope['test_profile_sha256']}"
    )


def render_proposal(proposal):
    validate_proposal(proposal)
    parts = [
        (
            f"Repository: `{proposal['repo']}`\n"
            f"Base commit: `{proposal['base_sha']}`\n"
            f"Revision: `{proposal['revision']}`"
        ),
        "### Summary\n\n" + _block(proposal["summary"], "text"),
        "### Explanation\n\n" + _block(proposal["explanation"], "text"),
        "### Proposed code\n\n" + _block(proposal["diff"], "diff"),
        (
            "### Review\n\n"
            "Write a comment below this issue with `Approve` or `Reject`. "
            "Any other text is feedback requesting a revised proposal.\n\n"
            "Approval covers only the revision shown above.\n\n"
            "This page renderer has not executed the proposed code."
        ),
        "### Proposal record\n\n" + _block(
            json.dumps(proposal, sort_keys=True, indent=2),
            "json",
        ),
    ]
    if "scope" in proposal:
        parts.insert(-1, "### Approval scope\n\n" + _block(
            format_test_scope(proposal["scope"]), "text",
        ))
    body = "\n\n".join(parts) + "\n"
    if len(body.encode("utf-8")) > MAX_ISSUE_BODY_BYTES:
        raise ValueError("Rendered proposal exceeds issue size limit")
    return body


def parse_proposal(body):
    if (
        not isinstance(body, str)
        or len(body.encode("utf-8")) > MAX_ISSUE_BODY_BYTES
    ):
        raise ValueError("Invalid proposal page")

    try:
        record = body.rsplit("\n\n### Proposal record\n\n", 1)[1]
        lines = record.splitlines()
        opening = re.fullmatch(r"(`{3,})json", lines[0])
        if not opening or lines[-1] != opening[1]:
            raise ValueError("Invalid proposal record block")
        proposal = json.loads("\n".join(lines[1:-1]))
    except (IndexError, ValueError, RecursionError):
        raise ValueError("Invalid proposal page") from None

    if render_proposal(proposal) != body:
        raise ValueError("Proposal page differs from its reviewed record")
    return proposal
