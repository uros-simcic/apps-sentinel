from datetime import datetime, timezone
import json
from unittest.mock import Mock

from config import load, validate
from github_client import APIError
from scan import scan


def run_demo(scenario):
    if scenario not in ("healthy", "failed", "unavailable"):
        raise ValueError("Unknown demo scenario")

    config = validate(load("config.example.json"))
    owner = {
        "id": config["owner_id"],
        "login": config["owner_login"],
    }
    api = Mock()

    if scenario == "unavailable":
        api.get.side_effect = [
            owner,
            APIError("Fixture access denied", 403),
        ]
    else:
        api.get.side_effect = [
            owner,
            {"default_branch": "main"},
            {"state": "active"},
            {"workflow_runs": [{
                "head_branch": "main",
                "status": "completed",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "conclusion": (
                    "success" if scenario == "healthy" else "failure"
                ),
            }]},
        ]

    return scan(config, api)


def main():
    for scenario in ("healthy", "failed", "unavailable"):
        print(json.dumps({
            "scenario": scenario,
            "report": run_demo(scenario),
        }, indent=2))


if __name__ == "__main__":
    main()
