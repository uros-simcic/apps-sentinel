import base64
import binascii
import json
from pathlib import PurePosixPath
from urllib.parse import quote

from checks import check_json
from github_client import APIError

MAX_JSON_BYTES = 65536


def check_repo_json(api, check, now=None):
    path = check["path"]
    if (
        not isinstance(path, str)
        or not path.endswith(".json")
        or "\\" in path
        or PurePosixPath(path).is_absolute()
        or any(part in ("", ".", "..") for part in path.split("/"))
    ):
        raise ValueError("Invalid repository JSON path")

    try:
        file = api.get(
            f"/repos/{check['repo']}/contents/{quote(path, safe='/')}"
        )
        if file["type"] != "file" or file["encoding"] != "base64":
            return "unknown", "Unsupported repository file evidence"
        encoded = file["content"].replace("\n", "").replace("\r", "")
        raw = base64.b64decode(encoded, validate=True)
    except APIError:
        return "unknown", "Repository JSON unavailable"
    except (KeyError, TypeError, AttributeError, ValueError, binascii.Error):
        return "unknown", "Malformed repository file evidence"

    if len(raw) > MAX_JSON_BYTES:
        return "unknown", "Repository JSON exceeds size limit"

    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        return "fail", "Application output is invalid JSON"

    return check_json(
        data, check["required_fields"], check["timestamp_field"],
        check["max_age_hours"], now,
    )
