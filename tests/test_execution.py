import unittest
from unittest.mock import Mock, patch

from execution import claim_execution
from state import StateError


class ExecutionClaimTests(unittest.TestCase):
    CONFIG = {"mode": "active"}
    APPROVED = {
        "proposal": {"revision": "b" * 64},
        "comment_id": 1,
    }

    def claim(self, api):
        return claim_execution(api, self.CONFIG, 7, 8, "b" * 64)

    def test_claim_is_saved_before_returning_approved_scope(self):
        api = Mock()
        original = {"schema_version": 1, "checks": []}
        with (
            patch("execution.check_approval", return_value=self.APPROVED),
            patch("execution.load_state", return_value=original),
            patch("execution.save_state") as saver,
        ):
            result = self.claim(api)
        self.assertEqual(result, self.APPROVED)
        state = saver.call_args.args[3]
        self.assertEqual(state["executions"], [{
            "proposal_issue": 8, "revision": "b" * 64,
            "comment_id": 1, "status": "claimed",
        }])
        self.assertEqual(original, {"schema_version": 1, "checks": []})

    def test_consumed_approval_cannot_be_claimed_again(self):
        for status in ("claimed", "succeeded", "failed", "uncertain"):
            state = {
                "schema_version": 2, "checks": [],
                "executions": [{
                    "proposal_issue": 8, "revision": "b" * 64,
                    "comment_id": 1, "status": status,
                }],
            }
            with (
                patch("execution.check_approval", return_value=self.APPROVED),
                patch("execution.load_state", return_value=state),
                patch("execution.save_state") as saver,
            ):
                with self.subTest(status=status), self.assertRaises(ValueError):
                    self.claim(Mock())
            saver.assert_not_called()

    def test_unconfirmed_claim_does_not_return_execution_scope(self):
        with (
            patch("execution.check_approval", return_value=self.APPROVED),
            patch("execution.load_state", return_value={
                "schema_version": 1, "checks": [],
            }),
            patch("execution.save_state", side_effect=StateError),
        ):
            with self.assertRaises(StateError):
                self.claim(Mock())

    def test_failed_approval_prevents_state_access(self):
        with (
            patch("execution.check_approval", side_effect=ValueError),
            patch("execution.load_state") as loader,
        ):
            with self.assertRaises(ValueError):
                self.claim(Mock())
        loader.assert_not_called()
