import json
import re
from pathlib import Path

MAX_CONFIG_BYTES = 65536


class ConfigError(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError("Duplicate configuration key")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ConfigError("Nonstandard JSON constant")


def load(path):
    try:
        with Path(path).open("rb") as source:
            raw = source.read(MAX_CONFIG_BYTES + 1)
    except OSError:
        raise ConfigError("Cannot read configuration") from None

    if len(raw) > MAX_CONFIG_BYTES:
        raise ConfigError("Configuration exceeds size limit")
    try:
        data = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise ConfigError("Invalid configuration JSON") from None

    if not isinstance(data, dict):
        raise ConfigError("Configuration must be an object")
    return data


def validate_identity(config):
    login = config.get("owner_login")
    owner_id = config.get("owner_id")
    repo = config.get("control_repo")

    if not isinstance(login, str) or not re.fullmatch(
        r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", login
    ):
        raise ConfigError("Invalid owner_login")

    if type(owner_id) is not int or owner_id <= 0:
        raise ConfigError("Invalid owner_id")

    if not isinstance(repo, str) or not re.fullmatch(
        r"[A-Za-z0-9-]+/[A-Za-z0-9_.-]+", repo
    ):
        raise ConfigError("Invalid control_repo")

    repo_owner, repo_name = repo.split("/")
    if repo_owner.lower() != login.lower():
        raise ConfigError("Control repository must belong to owner")
    if repo_name in (".", ".."):
        raise ConfigError("Invalid control_repo")
