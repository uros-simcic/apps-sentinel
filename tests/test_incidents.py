import unittest

from incidents import incident_key


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
