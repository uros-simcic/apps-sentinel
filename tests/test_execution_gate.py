import copy
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from approval import check_approval


class ExecutionGateTests(unittest.TestCase):
    def fixture(self):
        config = json.loads(Path("config.example.json").read_text())
        config["mode"] = "active"
        proposal = {
            "repo": config["apps"][0]["repo"],
            "base_sha": "a" * 40,
            "revision": "b" * 64,
        }
        reply = {
            "id": 1, "kind": "approve", "body": "Approve",
            "edited": False,
            "created_at": "2026-11-01T12:00:00+00:00",
            "updated_at": "2026-11-01T12:00:00+00:00",
        }
        review = {"proposal": proposal, "replies": [reply]}
        api = Mock()
        api.get.side_effect = [
            {"default_branch": "main"}, {"sha": "a" * 40},
        ]
        return api, config, review

    def check(self, api, config):
        return check_approval(api, config, 7, 8, "b" * 64)

    def test_current_unchanged_approval_returns_exact_scope(self):
        api, config, review = self.fixture()
        with patch("approval.read_replies", return_value=review) as reader:
            result = self.check(api, config)
        self.assertEqual(result, {
            "proposal": review["proposal"], "comment_id": 1,
        })
        self.assertEqual(reader.call_count, 2)
        api.create_issue.assert_not_called()
        api.update_issue_body.assert_not_called()

    def test_preview_stops_before_network(self):
        api, config, _ = self.fixture()
        config["mode"] = "preview"
        with patch("approval.read_replies") as reader:
            with self.assertRaises(ValueError):
                self.check(api, config)
        reader.assert_not_called()
        api.get.assert_not_called()

    def test_rejection_feedback_and_edited_approval_block_execution(self):
        for change in (
            {"kind": "reject"},
            {"kind": "feedback"},
            {"edited": True},
        ):
            api, config, review = self.fixture()
            review["replies"][0].update(change)
            with patch("approval.read_replies", return_value=review):
                with self.assertRaises(ValueError):
                    self.check(api, config)
            api.get.assert_not_called()

    def test_newer_edit_supersedes_approval(self):
        api, config, review = self.fixture()
        review["replies"].append({
            **review["replies"][0],
            "id": 2, "kind": "feedback", "edited": True,
            "updated_at": "2026-11-01T12:01:00+00:00",
        })
        with patch("approval.read_replies", return_value=review):
            with self.assertRaises(ValueError):
                self.check(api, config)
        api.get.assert_not_called()

    def test_changed_target_commit_blocks_execution(self):
        api, config, review = self.fixture()
        api.get.side_effect = [
            {"default_branch": "main"}, {"sha": "c" * 40},
        ]
        with patch("approval.read_replies", return_value=review):
            with self.assertRaises(ValueError):
                self.check(api, config)

    def test_changed_replies_during_review_block_execution(self):
        api, config, review = self.fixture()
        changed = copy.deepcopy(review)
        changed["replies"][0]["kind"] = "reject"
        with patch("approval.read_replies", side_effect=[review, changed]):
            with self.assertRaises(ValueError):
                self.check(api, config)
