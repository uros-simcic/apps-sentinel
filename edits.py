from difflib import unified_diff
import hashlib
import re

MAX_FILE_BYTES = 65536
MAX_DIFF_BYTES = 40960
MAX_EDIT_FILES = 5
MAX_CHANGED_LINES = 400


def build_edit(path, source, old_text, new_text, allowed_paths):
    if (
        not isinstance(path, str)
        or not re.fullmatch(r"[A-Za-z0-9_-][A-Za-z0-9_./-]*", path)
        or any(
            not part or part.startswith(".")
            for part in path.split("/")
        )
        or not isinstance(allowed_paths, (list, tuple, set, frozenset))
        or path not in allowed_paths
    ):
        raise ValueError("Edit path is not permitted")

    for value in (source, old_text, new_text):
        if (
            not isinstance(value, str)
            or "\x00" in value
            or "\r" in value
            or len(value.encode("utf-8")) > MAX_FILE_BYTES
        ):
            raise ValueError("Unsupported or oversized edit text")
    if not source.endswith("\n") or not old_text:
        raise ValueError("Existing LF text and a nonempty match are required")

    start = source.find(old_text)
    if start < 0 or start != source.rfind(old_text):
        raise ValueError("Old text must match exactly once")
    candidate = source.replace(old_text, new_text, 1)
    if (
        candidate == source
        or (candidate and not candidate.endswith("\n"))
        or len(candidate.encode("utf-8")) > MAX_FILE_BYTES
    ):
        raise ValueError("Invalid or oversized candidate")

    before = [line + "\n" for line in source.split("\n")[:-1]]
    after = [line + "\n" for line in candidate.split("\n")[:-1]]
    diff = "".join(unified_diff(
        before, after, fromfile="a/" + path, tofile="b/" + path,
    ))
    if len(diff.encode("utf-8")) > MAX_DIFF_BYTES:
        raise ValueError("Rendered edit exceeds diff limit")
    return {
        "path": path,
        "base_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "candidate": candidate,
        "diff": diff,
    }


def build_edits(edits, sources, allowed_paths):
    if (
        not isinstance(edits, list)
        or not 1 <= len(edits) <= MAX_EDIT_FILES
        or not isinstance(sources, dict)
    ):
        raise ValueError("Invalid edit batch")

    results = []
    seen = set()
    changed_lines = 0
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {
            "path", "base_sha256", "old_text", "new_text"
        }:
            raise ValueError("Invalid edit fields")
        path = edit["path"]
        if (
            not isinstance(path, str)
            or path in seen
            or path not in sources
            or not isinstance(edit["base_sha256"], str)
            or not re.fullmatch(r"[0-9a-f]{64}", edit["base_sha256"])
        ):
            raise ValueError("Invalid, duplicate or unavailable edit source")
        seen.add(path)

        result = build_edit(
            path, sources[path], edit["old_text"],
            edit["new_text"], allowed_paths,
        )
        if result["base_sha256"] != edit["base_sha256"]:
            raise ValueError("Edit source fingerprint does not match")
        changed_lines += sum(
            line.startswith(("+", "-"))
            for line in result["diff"].split("\n")[2:]
        )
        results.append(result)

    diff = "".join(result["diff"] for result in results)
    if (
        changed_lines > MAX_CHANGED_LINES
        or len(diff.encode("utf-8")) > MAX_DIFF_BYTES
    ):
        raise ValueError("Combined repair exceeds review limits")
    return {"edits": results, "diff": diff}
