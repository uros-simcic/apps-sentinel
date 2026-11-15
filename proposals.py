import hashlib
import json
import re

FIELDS = {"repo", "base_sha", "summary", "explanation", "diff"}
MAX_PROPOSAL_BYTES = 50000


def proposal_revision(record):
    if not isinstance(record, dict) or set(record) != FIELDS:
        raise ValueError("Invalid proposal fields")
    if any(
        not isinstance(value, str) or not value.strip()
        for value in record.values()
    ):
        raise ValueError("Proposal fields must contain text")
    if not re.fullmatch(
        r"[A-Za-z0-9-]+/[A-Za-z0-9_-][A-Za-z0-9_.-]*",
        record["repo"],
    ):
        raise ValueError("Invalid proposal repository")
    if not re.fullmatch(r"[0-9a-f]{40}", record["base_sha"]):
        raise ValueError("Invalid proposal base commit")
    if len(record["summary"]) > 160:
        raise ValueError("Proposal summary exceeds limit")

    encoded = json.dumps(
        record, sort_keys=True, ensure_ascii=True
    ).encode("utf-8")
    if len(encoded) > MAX_PROPOSAL_BYTES:
        raise ValueError("Proposal exceeds size limit")
    return hashlib.sha256(encoded).hexdigest()


def make_proposal(record):
    return {**record, "revision": proposal_revision(record)}


def validate_proposal(proposal):
    if (
        not isinstance(proposal, dict)
        or set(proposal) != FIELDS | {"revision"}
    ):
        raise ValueError("Invalid proposal record")
    record = {field: proposal[field] for field in FIELDS}
    if proposal["revision"] != proposal_revision(record):
        raise ValueError("Proposal revision does not match contents")
    return proposal
