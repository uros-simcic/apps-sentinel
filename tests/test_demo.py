import unittest
from unittest.mock import patch

from demo import run_demo


class DemoTests(unittest.TestCase):
    def test_complete_scan_with_fixture_evidence(self):
        with patch(
            "github_client.build_opener",
            side_effect=AssertionError("Demo must not create HTTP client"),
        ):
            for scenario, expected in (
                ("healthy", "pass"),
                ("failed", "fail"),
                ("unavailable", "unknown"),
            ):
                with self.subTest(scenario=scenario):
                    report = run_demo(scenario)
                    self.assertEqual(report["status"], expected)
                    self.assertEqual(
                        report["checks"][0]["status"], expected
                    )
