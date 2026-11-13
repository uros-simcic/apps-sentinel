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


def _fields(value, expected):
    if not isinstance(value, dict) or set(value) != expected:
        raise ConfigError("Missing or unknown configuration fields")


def validate(config):
    _fields(config, {
        "schema_version", "mode", "owner_login",
        "owner_id", "control_repo", "apps",
    })
    validate_identity(config)

    if type(config["schema_version"]) is not int or config["schema_version"] != 1:
        raise ConfigError("Unsupported schema_version")
    if config["mode"] not in ("preview", "active"):
        raise ConfigError("Invalid mode")

    apps = config["apps"]
    if not isinstance(apps, list) or not 1 <= len(apps) <= 100:
        raise ConfigError("Configure between one and 100 apps")

    app_ids = set()
    for app in apps:
        _fields(app, {"id", "repo", "checks"})
        name = app["id"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise ConfigError("Invalid app ID")
        if name in app_ids:
            raise ConfigError("Duplicate app ID")
        app_ids.add(name)
        validate_identity({**config, "control_repo": app["repo"]})

        checks = app["checks"]
        if not isinstance(checks, list) or not 1 <= len(checks) <= 100:
            raise ConfigError("Configure between one and 100 checks")

        check_ids = set()
        for check in checks:
            _fields(check, {
                "id", "kind", "repo", "workflow", "max_age_hours",
            })
            name = check["id"]
            if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", name):
                raise ConfigError("Invalid check ID")
            if name in check_ids:
                raise ConfigError("Duplicate check ID")
            check_ids.add(name)
            if check["kind"] != "workflow":
                raise ConfigError("Unsupported check kind")
            validate_identity({**config, "control_repo": check["repo"]})
            workflow = check["workflow"]
            if not isinstance(workflow, str) or not re.fullmatch(
                r"[A-Za-z0-9_-][A-Za-z0-9_.-]*\.ya?ml", workflow
            ):
                raise ConfigError("Invalid workflow filename")
            age = check["max_age_hours"]
            if type(age) not in (int, float) or not 0 < age <= 8760:
                raise ConfigError("Invalid workflow freshness limit")

    return config
