import hashlib
import json


def incident_key(result):
    if result.get("status") not in ("fail", "unknown"):
        raise ValueError("Only unresolved problems have incident keys")

    fields = ("repo", "check", "status", "detail")
    values = [result.get(field) for field in fields]
    if any(not isinstance(value, str) or not value.strip()
           for value in values):
        raise ValueError("Incomplete incident identity")

    values[0] = values[0].casefold()
    encoded = json.dumps(values, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def new_incidents(report, previous):
    known = {
        result["incident_id"]
        for result in previous["checks"]
        if result["status"] in ("fail", "unknown")
    }
    return [
        result for result in report["checks"]
        if result["status"] in ("fail", "unknown")
        and result["incident_id"] not in known
    ]
