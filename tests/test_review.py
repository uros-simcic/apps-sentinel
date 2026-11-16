import unittest
from unittest.mock import Mock, patch

from approval import read_replies


class ReviewTests(unittest.TestCase):
    CONFIG = {
        "owner_id": 12345,
        "control_repo": "example-owner/example-run",
    }

    def comment(self, comment_id=1, body="Approve", owner=12345):
        return {
            "id": comment_id,
            "body": body,
            "user": {"id": owner},
            "created_at": "2026-11-01T12:00:00Z",
            "updated_at": "2026-11-01T12:00:00Z",
        }

    def read(self, comments):
        api = Mock()
        api.pages.return_value = comments
        proposal = {"revision": "a" * 64}
        with patch("approval.load_proposal", return_value=proposal) as loader:
            result = read_replies(api, self.CONFIG, 7, 8, "a" * 64)
        loader.assert_called_once_with(
            api, self.CONFIG, 7, 8, "a" * 64
        )
        api.create_issue.assert_not_called()
        api.update_issue_body.assert_not_called()
        return result["replies"]

    def test_reads_owner_decisions_and_plain_feedback(self):
        replies = self.read([
            self.comment(3, "Keep the existing dependency"),
            self.comment(1, "Approve"),
            self.comment(2, "Reject"),
        ])
        self.assertEqual(
            [reply["kind"] for reply in replies],
            ["approve", "reject", "feedback"],
        )

    def test_non_owner_cannot_supply_a_decision(self):
        self.assertEqual(self.read([self.comment(owner=99999)]), [])

    def test_edited_approval_becomes_feedback(self):
        comment = self.comment()
        comment["updated_at"] = "2026-11-01T12:01:00Z"
        reply = self.read([comment])[0]
        self.assertEqual(reply["kind"], "feedback")
        self.assertTrue(reply["edited"])

    def test_invalid_comment_evidence_stops_processing(self):
        for change in (
            {"id": True},
            {"body": None},
            {"created_at": "invalid"},
            {"updated_at": "2026-11-01T11:00:00Z"},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.read([{**self.comment(), **change}])

    def test_duplicate_comment_ids_are_rejected(self):
        with self.assertRaises(ValueError):
            self.read([self.comment(), self.comment()])

    def test_invalid_proposal_blocks_comment_access(self):
        api = Mock()
        with patch("approval.load_proposal", side_effect=ValueError):
            with self.assertRaises(ValueError):
                read_replies(api, self.CONFIG, 7, 8, "a" * 64)
        api.pages.assert_not_called()
