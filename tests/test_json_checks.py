from datetime import datetime, timezone
import unittest

from checks import check_json


class JSONChecksTests(unittest.TestCase):
    NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)

    def check(self, data):
        return check_json(
            data, ["observation.temperature"],
            "measured_at", 2, self.NOW,
        )[0]

    def fixture(self, timestamp="2026-11-14T11:00:00Z"):
        return {
            "measured_at": timestamp,
            "observation": {"temperature": 0},
        }

    def test_fresh_output_accepts_zero(self):
        self.assertEqual(self.check(self.fixture()), "pass")

    def test_missing_and_null_values_fail(self):
        for value in ({}, {"temperature": None}):
            data = self.fixture()
            data["observation"] = value
            with self.subTest(value=value):
                self.assertEqual(self.check(data), "fail")

    def test_stale_output_fails(self):
        self.assertEqual(
            self.check(self.fixture("2026-11-14T08:00:00Z")), "fail"
        )

    def test_unreliable_timestamps_are_unknown(self):
        for timestamp in (
            "invalid",
            "2026-11-14T11:00:00",
            "2026-11-15T11:00:00Z",
        ):
            with self.subTest(timestamp=timestamp):
                self.assertEqual(
                    self.check(self.fixture(timestamp)), "unknown"
                )
