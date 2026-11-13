import copy
import json
from pathlib import Path
import unittest

from config import ConfigError, validate


class MonitorConfigTests(unittest.TestCase):
    def fixture(self):
        return json.loads(Path("config.example.json").read_text())

    def test_example_validates(self):
        config = self.fixture()
        self.assertEqual(validate(config), config)

    def test_invalid_top_level_settings(self):
        for change in (
            {"schema_version": True},
            {"mode": "automatic"},
            {"apps": []},
            {"unexpected": True},
        ):
            with self.subTest(change=change):
                config = self.fixture()
                config.update(change)
                with self.assertRaises(ConfigError):
                    validate(config)

    def test_duplicate_app_and_check_ids(self):
        for target in ("apps", "checks"):
            with self.subTest(target=target):
                config = self.fixture()
                items = (
                    config["apps"] if target == "apps"
                    else config["apps"][0]["checks"]
                )
                items.append(copy.deepcopy(items[0]))
                with self.assertRaises(ConfigError):
                    validate(config)

    def test_invalid_workflow_settings(self):
        for change in (
            {"repo": "someone-else/private-run"},
            {"workflow": "../daily.yml"},
            {"max_age_hours": True},
            {"max_age_hours": 0},
            {"max_age_hours": float("inf")},
            {"kind": "shell"},
            {"unexpected": True},
        ):
            with self.subTest(change=change):
                config = self.fixture()
                config["apps"][0]["checks"][0].update(change)
                with self.assertRaises(ConfigError):
                    validate(config)
