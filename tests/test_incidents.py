import unittest

from incidents import incident_key, new_incidents


class IncidentTests(unittest.TestCase):
    def fixture(self):
        return {
            "repo": "example-owner/example-app",
            "check": "output",
            "status": "fail",
            "detail": "Application output is stale",
        }

    def test_repeated_observations_keep_same_key(self):
        first = self.fixture()
        second = {**first, "observed_at": "another observation"}
        self.assertEqual(incident_key(first), incident_key(second))

    def test_repository_case_keeps_same_key(self):
        first = self.fixture()
        second = {**first, "repo": first["repo"].upper()}
        self.assertEqual(incident_key(first), incident_key(second))

    def test_different_problems_have_different_keys(self):
        first = self.fixture()
        for change in (
            {"check": "forecast"},
            {"status": "unknown"},
            {"detail": "Required application value is missing"},
        ):
            with self.subTest(change=change):
                self.assertNotEqual(
                    incident_key(first), incident_key({**first, **change})
                )

    def test_invalid_identity_is_rejected(self):
        for change in ({"status": "pass"}, {"repo": ""}, {"check": None}):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    incident_key({**self.fixture(), **change})

    def report(self, status):
        result = {**self.fixture(), "status": status}
        if status in ("fail", "unknown"):
            result["incident_id"] = incident_key(result)
        return {"checks": [result]}

    def test_first_problem_is_new(self):
        report = self.report("fail")
        self.assertEqual(
            new_incidents(report, {"checks": []}),
            report["checks"],
        )

    def test_continuing_problem_is_not_new(self):
        for status in ("fail", "unknown"):
            with self.subTest(status=status):
                report = self.report(status)
                self.assertEqual(new_incidents(report, report), [])

    def test_recovery_is_silent_and_recurrence_is_new(self):
        failed = self.report("fail")
        healthy = self.report("pass")
        self.assertEqual(new_incidents(healthy, failed), [])
        self.assertEqual(
            new_incidents(failed, healthy), failed["checks"]
        )
