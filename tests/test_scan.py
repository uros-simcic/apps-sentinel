from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from config import ConfigError
from scan import main, scan
from state import StateError


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
        self.assertEqual(report["repair_candidates"], [])
        self.assertEqual(report["new_coverage_gaps"], [])

    def test_missing_evidence_is_not_healthy(self):
        with patch("scan.check_workflow", return_value=("unknown", "No access")):
            report = scan(self.fixture(), self.api())
        self.assertEqual(report["status"], "unknown")
        self.assertEqual(report["repair_candidates"], [])
        self.assertEqual(report["new_coverage_gaps"], report["checks"])
        self.assertRegex(report["checks"][0]["incident_id"], r"^[0-9a-f]{64}$")

    def test_failed_check_is_reported(self):
        with patch("scan.check_workflow", return_value=("fail", "Stale")):
            report = scan(self.fixture(), self.api())
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["repair_candidates"], report["checks"])
        self.assertEqual(report["new_coverage_gaps"], [])
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

    def test_scan_distinguishes_new_and_continuing_problems(self):
        with patch("scan.check_workflow", return_value=("fail", "Stale")):
            first = scan(self.fixture(), self.api())
            repeated = scan(self.fixture(), self.api(), previous=first)
        self.assertEqual(first["new_incidents"], first["checks"])
        self.assertEqual(repeated["new_incidents"], [])
        self.assertEqual(repeated["repair_candidates"], [])
        self.assertEqual(repeated["new_coverage_gaps"], [])

    def test_scan_recovery_and_recurrence(self):
        with patch("scan.check_workflow", return_value=("fail", "Stale")):
            failed = scan(self.fixture(), self.api())
        with patch("scan.check_workflow", return_value=("pass", "OK")):
            recovered = scan(self.fixture(), self.api(), previous=failed)
        with patch("scan.check_workflow", return_value=("fail", "Stale")):
            recurred = scan(self.fixture(), self.api(), previous=recovered)
        self.assertEqual(recovered["new_incidents"], [])
        self.assertEqual(recurred["new_incidents"], recurred["checks"])

    def test_preview_uses_saved_state_without_updating_it(self):
        previous = {"schema_version": 1, "checks": []}
        report = {"status": "pass", "checks": []}
        with (
            patch("scan.GitHub") as client,
            patch("scan.load_state", return_value=previous) as loader,
            patch("scan.scan", return_value=report) as scanner,
            redirect_stdout(io.StringIO()),
        ):
            result = main([
                "scan", "--config", "config.example.json",
                "--state-issue", "7",
            ])
        self.assertEqual(result, 0)
        loader.assert_called_once_with(
            client.return_value, self.fixture(), 7
        )
        scanner.assert_called_once_with(
            self.fixture(), client.return_value, previous=previous
        )
        client.return_value.update_issue_body.assert_not_called()

    def test_unreadable_state_stops_before_application_checks(self):
        with (
            patch("scan.GitHub") as client,
            patch("scan.load_state", side_effect=StateError("Unavailable")),
            patch("scan.scan") as scanner,
            redirect_stderr(io.StringIO()),
        ):
            result = main([
                "scan", "--config", "config.example.json",
                "--state-issue", "7",
            ])
        self.assertEqual(result, 2)
        scanner.assert_not_called()
        client.return_value.update_issue_body.assert_not_called()

    def test_scan_without_state_does_not_load_or_update_state(self):
        with (
            patch("scan.GitHub") as client,
            patch("scan.load_state") as loader,
            patch("scan.scan", return_value={"status": "pass"}),
            redirect_stdout(io.StringIO()),
        ):
            result = main(["scan", "--config", "config.example.json"])
        self.assertEqual(result, 0)
        loader.assert_not_called()
        client.return_value.update_issue_body.assert_not_called()
