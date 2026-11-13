from pathlib import Path
import tempfile
import unittest

from config import (
    ConfigError, MAX_CONFIG_BYTES, load, validate_identity,
)


class ConfigTests(unittest.TestCase):
    def test_valid_object(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_bytes(b'{"apps": [], "mode": "preview"}')
            self.assertEqual(
                load(path), {"apps": [], "mode": "preview"}
            )

    def test_invalid_configuration(self):
        cases = (
            b'{"owner": 1, "owner": 2}',
            b'{"nested": {"id": 1, "id": 2}}',
            b'{"value": NaN}',
            b'{"value": Infinity}',
            b'{"unfinished":',
            b'[]',
            b'\xff',
            b' ' * (MAX_CONFIG_BYTES + 1),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            for raw in cases:
                with self.subTest(raw_size=len(raw)):
                    path.write_bytes(raw)
                    with self.assertRaises(ConfigError):
                        load(path)

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ConfigError):
                load(Path(directory) / "missing.json")

    def test_valid_identity(self):
        validate_identity({
            "owner_login": "example-owner",
            "owner_id": 12345,
            "control_repo": "example-owner/sentinel-run",
        })

    def test_invalid_identity(self):
        valid = {
            "owner_login": "example-owner",
            "owner_id": 12345,
            "control_repo": "example-owner/sentinel-run",
        }
        cases = (
            {"owner_login": "-invalid"},
            {"owner_id": True},
            {"owner_id": 0},
            {"owner_id": "12345"},
            {"control_repo": "someone-else/sentinel-run"},
            {"control_repo": "example-owner/../secret"},
            {"control_repo": "example-owner/.."},
        )
        for change in cases:
            with self.subTest(change=change):
                with self.assertRaises(ConfigError):
                    validate_identity({**valid, **change})
