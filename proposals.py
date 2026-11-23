import hashlib
import json
import re

FIELDS = {"repo", "base_sha", "summary", "explanation", "diff"}
MAX_PROPOSAL_BYTES = 50000
SCOPE_FIELDS = {"operation", "base_branch", "test_profile", "test_profile_sha256"}


def _validate_scope(scope):
    if (
        not isinstance(scope, dict)
        or set(scope) != SCOPE_FIELDS
        or scope["operation"] != "test_only"
    ):
        raise ValueError("Invalid proposal approval scope")
    for field, pattern in (
        ("base_branch", r"[A-Za-z0-9_-]+(?:[./][A-Za-z0-9_-]+)*"),
        ("test_profile", r"[A-Za-z0-9_-]{1,64}"),
        ("test_profile_sha256", r"[0-9a-f]{64}"),
    ):
        value = scope[field]
        if not isinstance(value, str) or not re.fullmatch(pattern, value):
            raise ValueError("Invalid proposal scope field: " + field)


def proposal_revision(record):
    if not isinstance(record, dict) or set(record) not in (
        FIELDS, FIELDS | {"scope"},
    ):
        raise ValueError("Invalid proposal fields")
    if "scope" in record:
        _validate_scope(record["scope"])
    if any(
        not isinstance(record[field], str) or not record[field].strip()
        for field in FIELDS
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
    if not isinstance(proposal, dict) or "revision" not in proposal:
        raise ValueError("Invalid proposal record")
    record = {key: value for key, value in proposal.items() if key != "revision"}
    if proposal["revision"] != proposal_revision(record):
        raise ValueError("Proposal revision does not match contents")
    return proposal
