import base64
from datetime import datetime, timezone
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from config import ConfigError, validate
from github_client import APIError
from scan import scan


class JSONScanTests(unittest.TestCase):
    def fixture(self):
        config = json.loads(Path("config.example.json").read_text())
        config["apps"][0]["checks"] = [{
            "id": "output",
            "kind": "repo_json",
            "repo": "example-owner/example-app",
            "path": "docs/now.json",
            "required_fields": ["temperature"],
            "timestamp_field": "measured_at",
            "max_age_hours": 2,
        }]
        return config

    def api(self, payload):
        api = Mock()
        api.get.side_effect = [
            {"id": 12345, "login": "example-owner"},
            {
                "type": "file",
                "encoding": "base64",
                "content": base64.b64encode(json.dumps(payload).encode()).decode(),
            },
        ]
        return api

    def test_scanner_reads_repository_output(self):
        api = self.api({
            "temperature": 0,
            "measured_at": datetime.now(timezone.utc).isoformat(),
        })
        report = scan(self.fixture(), api)
        self.assertEqual(report["status"], "pass")
        self.assertEqual(api.get.call_count, 2)
        self.assertEqual(
            api.get.call_args.args[0],
            "/repos/example-owner/example-app/contents/docs/now.json",
        )

    def test_missing_application_value_fails_scan(self):
        report = scan(self.fixture(), self.api({
            "measured_at": datetime.now(timezone.utc).isoformat(),
        }))
        self.assertEqual(report["status"], "fail")

    def test_missing_access_is_unknown(self):
        api = Mock()
        api.get.side_effect = [
            {"id": 12345, "login": "example-owner"},
            APIError("Unavailable", 403),
        ]
        self.assertEqual(scan(self.fixture(), api)["status"], "unknown")

    def test_invalid_json_configuration_is_rejected(self):
        for change in (
            {"path": "../private.json"},
            {"required_fields": []},
            {"required_fields": ["temperature", "temperature"]},
            {"timestamp_field": ""},
        ):
            with self.subTest(change=change):
                config = self.fixture()
                config["apps"][0]["checks"][0].update(change)
                with self.assertRaises(ConfigError):
                    validate(config)
