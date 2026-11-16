import base64
import hashlib
import re

from config import validate
from edits import MAX_FILE_BYTES, build_edits, validate_edit_path
from proposal_page import render_proposal
from proposals import make_proposal

MAX_SOURCE_FILES = 8
MAX_SOURCE_BYTES = 120 * 1024


def read_sources(api, config, repo, base_sha, paths, allowed_paths):
    validate(config)
    targets = {
        name.casefold()
        for app in config["apps"]
        for name in [app["repo"], *[c["repo"] for c in app["checks"]]]
    }
    if (
        not isinstance(repo, str) or repo.casefold() not in targets
        or not isinstance(base_sha, str)
        or not re.fullmatch(r"[0-9a-f]{40}", base_sha)
        or not isinstance(paths, list)
        or not 1 <= len(paths) <= MAX_SOURCE_FILES
    ):
        raise ValueError("Invalid source request")
    for path in paths:
        validate_edit_path(path, allowed_paths)
    if len(set(paths)) != len(paths):
        raise ValueError("Duplicate source path")

    owner = api.get("/user")
    if (
        not isinstance(owner, dict)
        or type(owner.get("id")) is not int
        or owner["id"] != config["owner_id"]
        or not isinstance(owner.get("login"), str)
        or owner["login"].casefold() != config["owner_login"].casefold()
    ):
        raise ValueError("Source credential does not match owner")

    base = "/repos/" + repo
    commit = api.get(base + "/commits/" + base_sha)
    try:
        tree_sha = commit["commit"]["tree"]["sha"]
    except (KeyError, TypeError):
        raise ValueError("Invalid source commit") from None
    if (
        commit.get("sha") != base_sha
        or not isinstance(tree_sha, str)
        or not re.fullmatch(r"[0-9a-f]{40}", tree_sha)
    ):
        raise ValueError("Source commit does not match requested base")

    tree = api.get(base + "/git/trees/" + tree_sha + "?recursive=1")
    if (
        not isinstance(tree, dict)
        or tree.get("sha") != tree_sha
        or tree.get("truncated") is not False
        or not isinstance(tree.get("tree"), list)
        or any(not isinstance(entry, dict) for entry in tree["tree"])
    ):
        raise ValueError("Incomplete source tree")

    sources = {}
    fingerprints = {}
    total = 0
    for path in paths:
        matches = [entry for entry in tree["tree"] if entry.get("path") == path]
        if len(matches) != 1:
            raise ValueError("Source path is missing or ambiguous")
        entry = matches[0]
        if (
            entry.get("type") != "blob"
            or entry.get("mode") not in ("100644", "100755")
            or type(entry.get("size")) is not int
            or not 0 <= entry["size"] <= MAX_FILE_BYTES
            or not isinstance(entry.get("sha"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", entry["sha"])
        ):
            raise ValueError("Source must be a bounded regular file")

        blob = api.get(base + "/git/blobs/" + entry["sha"])
        try:
            if (
                blob["sha"] != entry["sha"]
                or blob["encoding"] != "base64"
                or type(blob["size"]) is not int
                or blob["size"] != entry["size"]
            ):
                raise ValueError("Invalid source blob metadata")
            encoded = blob["content"].replace("\n", "").replace("\r", "")
            raw = base64.b64decode(encoded, validate=True)
            header = f"blob {len(raw)}\0".encode()
            if (
                len(raw) != entry["size"]
                or hashlib.sha1(header + raw).hexdigest() != entry["sha"]
            ):
                raise ValueError("Source blob fingerprint mismatch")
            text = raw.decode("utf-8")
        except (KeyError, TypeError, AttributeError, ValueError):
            raise ValueError("Invalid source blob evidence") from None
        if "\x00" in text or "\r" in text or not text.endswith("\n"):
            raise ValueError("Source must be existing UTF-8 LF text")

        total += len(raw)
        if total > MAX_SOURCE_BYTES:
            raise ValueError("Source bundle exceeds size limit")
        sources[path] = text
        fingerprints[path] = hashlib.sha256(raw).hexdigest()

    return {
        "repo": repo,
        "base_sha": base_sha,
        "sources": sources,
        "fingerprints": fingerprints,
    }


def prepare_repair(
    api, config, repo, base_sha, paths, allowed_paths, answer
):
    if (
        not isinstance(answer, dict)
        or set(answer) != {"summary", "explanation", "edits"}
    ):
        raise ValueError("Invalid repair answer")

    bundle = read_sources(
        api, config, repo, base_sha, paths, allowed_paths
    )
    repair = build_edits(
        answer["edits"], bundle["sources"], allowed_paths
    )
    proposal = make_proposal({
        "repo": bundle["repo"],
        "base_sha": bundle["base_sha"],
        "summary": answer["summary"],
        "explanation": answer["explanation"],
        "diff": repair["diff"],
    })
    render_proposal(proposal)
    return proposal
