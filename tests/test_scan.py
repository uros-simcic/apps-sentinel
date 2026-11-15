from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from config import ConfigError
from scan import main, scan


class ScanTests(unittest.TestCase):
    def fixture(self):
        return json.loads(Path("config.example.json").read_text())

    def api(self):
        api = Mock()
        api.get.return_value = {
            "id": 12345,
            "login": "example-owner",
        }
        return api

    def test_offline_validation_never_creates_client(self):
        with patch("scan.GitHub") as client:
            with redirect_stdout(io.StringIO()):
                result = main([
                    "validate", "--config", "config.example.json",
                ])
            self.assertEqual(result, 0)
            client.assert_not_called()

    def test_successful_scan(self):
        with patch("scan.check_workflow", return_value=("pass", "OK")):
            report = scan(self.fixture(), self.api())
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["checks"][0]["app"], "example-app")
        self.assertNotIn("incident_id", report["checks"][0])

    def test_missing_evidence_is_not_healthy(self):
        with patch("scan.check_workflow", return_value=("unknown", "No access")):
            report = scan(self.fixture(), self.api())
        self.assertEqual(report["status"], "unknown")
        self.assertRegex(report["checks"][0]["incident_id"], r"^[0-9a-f]{64}$")

    def test_failed_check_is_reported(self):
        with patch("scan.check_workflow", return_value=("fail", "Stale")):
            report = scan(self.fixture(), self.api())
        self.assertEqual(report["status"], "fail")
        self.assertRegex(report["checks"][0]["incident_id"], r"^[0-9a-f]{64}$")

    def test_repeated_failure_keeps_same_incident(self):
        with patch("scan.check_workflow", return_value=("fail", "Stale")):
            first = scan(self.fixture(), self.api())
            second = scan(self.fixture(), self.api())
        self.assertEqual(
            first["checks"][0]["incident_id"],
            second["checks"][0]["incident_id"],
        )

    def test_wrong_owner_blocks_checks(self):
        api = self.api()
        api.get.return_value["id"] = 99999
        with patch("scan.check_workflow") as check:
            with self.assertRaises(ConfigError):
                scan(self.fixture(), api)
            check.assert_not_called()

    def test_active_mode_is_blocked_before_network(self):
        config = self.fixture()
        config["mode"] = "active"
        api = self.api()
        with self.assertRaises(ConfigError):
            scan(config, api)
        api.get.assert_not_called()
