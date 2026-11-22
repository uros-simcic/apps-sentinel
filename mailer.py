from email.headerregistry import Address
from email.errors import HeaderParseError
from email.message import EmailMessage
from email.policy import SMTP
import hashlib
import re

from config import validate
from proposal_page import render_proposal
from proposal_store import load_proposal


def _address(value):
    if (
        not isinstance(value, str)
        or not 3 <= len(value) <= 254
        or any(ord(char) <= 32 or ord(char) >= 127 for char in value)
    ):
        raise ValueError("Invalid email address")
    try:
        address = Address(addr_spec=value)
    except (ValueError, IndexError, HeaderParseError):
        raise ValueError("Invalid email address") from None
    if (
        not address.username or not address.domain
        or address.addr_spec != value
    ):
        raise ValueError("Use a single bare email address")
    return address


def build_proposal_email(
    config, proposal, issue_url, sender, recipient
):
    validate(config)
    render_proposal(proposal)
    targets = {
        repo.casefold()
        for app in config["apps"]
        for repo in [app["repo"], *[c["repo"] for c in app["checks"]]]
    }
    if proposal["repo"].casefold() not in targets:
        raise ValueError("Email target is not monitored")

    prefix = (
        "https://github.com/" + config["control_repo"] + "/issues/"
    )
    if (
        not isinstance(issue_url, str)
        or not issue_url.startswith(prefix)
        or not re.fullmatch(r"[1-9][0-9]*", issue_url[len(prefix):])
    ):
        raise ValueError("Invalid approval link")

    summary = " ".join(proposal["summary"].split())
    if any(ord(char) < 32 or ord(char) == 127 for char in summary):
        raise ValueError("Invalid email subject")

    message = EmailMessage(policy=SMTP)
    message["From"] = _address(sender)
    message["To"] = _address(recipient)
    message["Subject"] = (
        f"[{proposal['repo']}] {summary} — proposed solution"
    )
    message.set_content(
        f"{proposal['summary']}\n\n"
        f"{proposal['explanation']}\n\n"
        f"Base commit: {proposal['base_sha']}\n"
        f"Proposal revision: {proposal['revision']}\n\n"
        "Validation: the proposed code has not been executed.\n\n"
        f"Proposed code:\n{proposal['diff']}\n"
        f"Review and respond:\n{issue_url}\n\n"
        "Open the link and write Approve, Reject, or feedback "
        "in the issue's comment box.\n"
        "Approval covers only the displayed proposal revision.\n"
        "Replies to this email are not read.\n"
    )
    return message


def prepare_proposal_email(
    api, config, state_issue, number, revision, sender, recipient
):
    proposal = load_proposal(
        api, config, state_issue, number, revision
    )
    url = (
        f"https://github.com/{config['control_repo']}/issues/{number}"
    )
    message = build_proposal_email(
        config, proposal, url, sender, recipient
    )
    identifier = hashlib.sha256(
        (url + "\n" + proposal["revision"]).encode("utf-8")
    ).hexdigest()
    message["Message-ID"] = f"<{identifier}@apps-sentinel.invalid>"
    return message
