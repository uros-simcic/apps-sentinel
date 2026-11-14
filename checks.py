from datetime import datetime, timezone
from urllib.parse import quote, urlencode

from github_client import APIError


def check_workflow(api, check, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Timezone-aware observation time required")

    repo = check["repo"]
    workflow = quote(check["workflow"], safe="")
    base = f"/repos/{repo}"

    try:
        repository = api.get(base)
        branch = repository["default_branch"]
        metadata = api.get(f"{base}/actions/workflows/{workflow}")
        if metadata["state"] != "active":
            return "unknown", "Workflow is not active"

        query = urlencode({
            "branch": branch,
            "status": "completed",
            "per_page": 1,
        })
        data = api.get(
            f"{base}/actions/workflows/{workflow}/runs?{query}"
        )
        runs = data["workflow_runs"]
        if not isinstance(runs, list) or not runs:
            return "unknown", "No completed workflow run"

        run = runs[0]
        if run["head_branch"] != branch or run["status"] != "completed":
            return "unknown", "Unexpected workflow evidence"

        created = datetime.fromisoformat(
            run["created_at"].replace("Z", "+00:00")
        )
        if created.tzinfo is None or created.utcoffset() is None:
            return "unknown", "Workflow timestamp lacks timezone"

        age = (now - created).total_seconds() / 3600
        if age < 0:
            return "unknown", "Workflow timestamp is in the future"
        if age > check["max_age_hours"]:
            return "fail", "Latest completed workflow run is stale"

        conclusion = run["conclusion"]
        if conclusion == "success":
            return "pass", "Recent workflow run succeeded"
        if conclusion in (
            "failure", "timed_out", "action_required", "startup_failure",
        ):
            return "fail", "Latest workflow run failed"
        return "unknown", "Workflow did not establish success"

    except APIError:
        return "unknown", "GitHub workflow evidence unavailable"
    except (KeyError, TypeError, ValueError, AttributeError):
        return "unknown", "Malformed workflow evidence"
