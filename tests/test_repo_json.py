import base64
from datetime import datetime, timezone
import unittest
from unittest.mock import Mock

from github_client import APIError
from repo_json import check_repo_json, MAX_JSON_BYTES


class RepoJSONTests(unittest.TestCase):
    NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
    CHECK = {
        "repo": "example-owner/weather",
        "path": "docs/now.json",
        "required_fields": ["temperature"],
        "timestamp_field": "measured_at",
        "max_age_hours": 2,
    }

    def api(self, raw):
        api = Mock()
        api.get.return_value = {
            "type": "file",
            "encoding": "base64",
            "content": base64.b64encode(raw).decode(),
        }
        return api

    def test_fresh_repository_output_passes(self):
        api = self.api(
            b'{"temperature":0,"measured_at":"2026-11-14T11:00:00Z"}'
        )
        self.assertEqual(
            check_repo_json(api, self.CHECK, self.NOW)[0], "pass"
        )
        api.get.assert_called_once_with(
            "/repos/example-owner/weather/contents/docs/now.json"
        )

    def test_invalid_application_json_fails(self):
        self.assertEqual(
            check_repo_json(self.api(b"invalid"), self.CHECK, self.NOW)[0],
            "fail",
        )

    def test_invalid_or_unsupported_values_fail_without_raising(self):
        for value in (b"NaN", b"Infinity", b"-Infinity", b"1e400", b"9" * 4500):
            raw = (
                b'{"temperature":' + value
                + b',"measured_at":"2026-11-14T11:00:00Z"}'
            )
            with self.subTest(value=value[:20]):
                self.assertEqual(
                    check_repo_json(self.api(raw), self.CHECK, self.NOW)[0],
                    "fail",
                )

    def test_duplicate_fields_fail_instead_of_using_last_value(self):
        raw = (
            b'{"temperature":null,"temperature":0,'
            b'"measured_at":"2026-11-14T11:00:00Z"}'
        )
        self.assertEqual(
            check_repo_json(self.api(raw), self.CHECK, self.NOW)[0], "fail"
        )

    def test_oversized_output_is_unknown(self):
        self.assertEqual(
            check_repo_json(
                self.api(b" " * (MAX_JSON_BYTES + 1)),
                self.CHECK, self.NOW,
            )[0],
            "unknown",
        )

    def test_access_failure_is_unknown(self):
        api = Mock()
        api.get.side_effect = APIError("Unavailable", 403)
        self.assertEqual(
            check_repo_json(api, self.CHECK, self.NOW)[0], "unknown"
        )

    def test_traversal_is_blocked_before_network(self):
        api = Mock()
        with self.assertRaises(ValueError):
            check_repo_json(
                api, {**self.CHECK, "path": "../private.json"}, self.NOW
            )
        api.get.assert_not_called()
