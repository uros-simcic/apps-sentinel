import re
from urllib.parse import quote

from config import validate
from proposal_page import parse_proposal, render_proposal
from state import load_state


def publish_proposal(api, config, state_issue, proposal):
    validate(config)
    if config["mode"] != "active":
        raise ValueError("Proposal publishing requires active mode")

    body = render_proposal(proposal)
    targets = {
        repo.casefold()
        for app in config["apps"]
        for repo in [app["repo"], *[c["repo"] for c in app["checks"]]]
    }
    if proposal["repo"].casefold() not in targets:
        raise ValueError("Proposal target is not monitored")

    load_state(api, config, state_issue)
    target = "/repos/" + proposal["repo"]
    repo = api.get(target)
    branch = repo.get("default_branch") if isinstance(repo, dict) else None
    if not isinstance(branch, str) or not branch:
        raise ValueError("Missing target default branch")
    head = api.get(target + "/commits/" + quote(branch, safe=""))
    if not isinstance(head, dict) or head.get("sha") != proposal["base_sha"]:
        raise ValueError("Proposal base commit is no longer current")

    title = (
        proposal["repo"] + ": " + " ".join(proposal["summary"].split())
    )[:240]
    path = "/repos/" + config["control_repo"] + "/issues"
    issues = api.pages(
        path + "?state=all&per_page=100&creator="
        + quote(config["owner_login"], safe="")
    )
    if not isinstance(issues, list):
        raise ValueError("Invalid proposal issue listing")

    matches = []
    for issue in issues:
        if not isinstance(issue, dict):
            raise ValueError("Malformed proposal issue evidence")
        actor = issue.get("user")
        if (
            "pull_request" not in issue
            and issue.get("body") == body
            and isinstance(actor, dict)
            and type(actor.get("id")) is int
            and actor["id"] == config["owner_id"]
        ):
            matches.append(issue)

    if len(matches) > 1:
        raise ValueError("Multiple issues contain the same proposal")
    if matches and matches[0].get("state") != "open":
        raise ValueError("Matching proposal is already closed")

    created = matches[0] if matches else api.create_issue(path, title, body)
    if not isinstance(created, dict):
        raise ValueError("GitHub did not confirm proposal creation")

    number = created.get("number")
    actor = created.get("user")
    url = (
        f"https://github.com/{config['control_repo']}/issues/{number}"
    )
    if (
        type(number) is not int or number <= 0
        or not isinstance(actor, dict)
        or type(actor.get("id")) is not int
        or actor["id"] != config["owner_id"]
        or created.get("state") != "open"
        or "pull_request" in created
        or created.get("title") != title
        or created.get("body") != body
        or not isinstance(created.get("html_url"), str)
        or created["html_url"].casefold() != url.casefold()
    ):
        raise ValueError("GitHub did not confirm the intended proposal")
    return {"number": number, "url": url, "revision": proposal["revision"]}


def load_proposal(api, config, state_issue, number, revision):
    validate(config)
    if (
        type(number) is not int or number <= 0
        or not isinstance(revision, str)
        or not re.fullmatch(r"[0-9a-f]{64}", revision)
    ):
        raise ValueError("Invalid proposal reference")

    load_state(api, config, state_issue)
    issue = api.get(
        f"/repos/{config['control_repo']}/issues/{number}"
    )
    if not isinstance(issue, dict):
        raise ValueError("Invalid proposal issue")
    actor = issue.get("user")
    if (
        type(issue.get("number")) is not int
        or issue["number"] != number
        or issue.get("state") != "open"
        or "pull_request" in issue
        or not isinstance(actor, dict)
        or type(actor.get("id")) is not int
        or actor["id"] != config["owner_id"]
    ):
        raise ValueError("Invalid owner-controlled proposal issue")

    proposal = parse_proposal(issue.get("body"))
    if proposal["revision"] != revision:
        raise ValueError("Proposal does not match the recorded revision")

    targets = {
        repo.casefold()
        for app in config["apps"]
        for repo in [app["repo"], *[c["repo"] for c in app["checks"]]]
    }
    if proposal["repo"].casefold() not in targets:
        raise ValueError("Proposal target is not monitored")
    return proposal
