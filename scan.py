import argparse
from datetime import datetime, timezone
import json
import os
import sys

from checks import check_workflow
from config import ConfigError, load, validate
from github_client import APIError, GitHub
from incidents import incident_key
from repo_json import check_repo_json


def scan(config, api):
    validate(config)
    if config["mode"] != "preview":
        raise ConfigError("Only preview scans are currently supported")

    owner = api.get("/user")
    if not isinstance(owner, dict):
        raise APIError("Invalid GitHub identity response")
    if (
        type(owner.get("id")) is not int
        or owner["id"] != config["owner_id"]
        or not isinstance(owner.get("login"), str)
        or owner["login"].casefold() != config["owner_login"].casefold()
    ):
        raise ConfigError("GitHub credential does not match configured owner")

    observed = datetime.now(timezone.utc)
    results = []
    for app in config["apps"]:
        for check in app["checks"]:
            handler = (
                check_workflow if check["kind"] == "workflow"
                else check_repo_json
            )
            status, detail = handler(api, check, observed)
            result = {
                "app": app["id"],
                "repo": check["repo"],
                "check": check["id"],
                "status": status,
                "detail": detail,
            }
            if status in ("fail", "unknown"):
                result["incident_id"] = incident_key(result)
            results.append(result)

    statuses = {result["status"] for result in results}
    overall = (
        "fail" if "fail" in statuses
        else "unknown" if "unknown" in statuses
        else "pass"
    )
    return {
        "mode": "preview",
        "observed_at": observed.isoformat(),
        "status": overall,
        "checks": results,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate", "scan"))
    parser.add_argument("--config", default="config.json")
    args = parser.parse_args(argv)

    try:
        config = validate(load(args.config))
        if args.command == "validate":
            print(json.dumps({"status": "valid", "mode": config["mode"]}))
            return 0

        report = scan(config, GitHub(os.environ.get("READ_TOKEN")))
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "pass" else 1
    except (ConfigError, APIError, ValueError) as exc:
        print("Scan stopped: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
