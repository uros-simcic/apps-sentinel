from datetime import datetime, timezone
import unittest
from unittest.mock import Mock

from checks import check_workflow
from github_client import APIError


class WorkflowTests(unittest.TestCase):
    NOW = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
    CHECK = {
        "repo": "example-owner/example-app-run",
        "workflow": "daily.yml",
        "max_age_hours": 36,
    }

    def api(self, **changes):
        run = {
            "head_branch": "main",
            "status": "completed",
            "created_at": "2026-11-13T10:00:00Z",
            "conclusion": "success",
        }
        run.update(changes)
        api = Mock()
        api.get.side_effect = [
            {"default_branch": "main"},
            {"state": "active"},
            {"workflow_runs": [run]},
        ]
        return api

    def test_recent_success_passes(self):
        api = self.api()
        self.assertEqual(
            check_workflow(api, self.CHECK, self.NOW)[0], "pass"
        )
        self.assertIn("branch=main", api.get.call_args.args[0])

    def test_failed_and_stale_runs_fail(self):
        for changes in (
            {"conclusion": "failure"},
            {"created_at": "2026-11-10T10:00:00Z"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(
                    check_workflow(
                        self.api(**changes), self.CHECK, self.NOW
                    )[0],
                    "fail",
                )

    def test_unreliable_evidence_is_unknown(self):
        for changes in (
            {"head_branch": "feature"},
            {"created_at": "invalid"},
            {"created_at": "2026-11-14T10:00:00Z"},
            {"conclusion": "skipped"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(
                    check_workflow(
                        self.api(**changes), self.CHECK, self.NOW
                    )[0],
                    "unknown",
                )

    def test_missing_access_is_unknown(self):
        api = Mock()
        api.get.side_effect = APIError("Unavailable", 403)
        self.assertEqual(
            check_workflow(api, self.CHECK, self.NOW)[0], "unknown"
        )
