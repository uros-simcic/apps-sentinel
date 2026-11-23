import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from execution import claim_execution, finish_execution
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

    def test_new_comment_cannot_claim_same_revision(self):
        approved = {**self.APPROVED, "comment_id": 2}
        for status in ("claimed", "succeeded", "failed", "uncertain"):
            state = {
                "schema_version": 2, "checks": [],
                "executions": [{
                    "proposal_issue": 8, "revision": "b" * 64,
                    "comment_id": 1, "status": status,
                }],
            }
            with (
                self.subTest(status=status),
                patch("execution.check_approval", return_value=approved),
                patch("execution.load_state", return_value=state),
                patch("execution.save_state") as saver,
            ):
                with self.assertRaisesRegex(ValueError, "already been claimed"):
                    self.claim(Mock())
                saver.assert_not_called()

    def test_distinct_approved_revision_can_be_claimed(self):
        revision = "c" * 64
        approved = {"proposal": {"revision": revision}, "comment_id": 2}
        state = {
            "schema_version": 2, "checks": [],
            "executions": [{
                "proposal_issue": 8, "revision": "b" * 64,
                "comment_id": 1, "status": "succeeded",
            }],
        }
        with (
            patch("execution.check_approval", return_value=approved),
            patch("execution.load_state", return_value=state),
            patch("execution.save_state") as saver,
        ):
            self.assertEqual(
                claim_execution(Mock(), self.CONFIG, 7, 8, revision), approved
            )
        self.assertEqual(saver.call_args.args[3]["executions"], [
            *state["executions"],
            {
                "proposal_issue": 8, "revision": revision,
                "comment_id": 2, "status": "claimed",
            },
        ])

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


class ExecutionOutcomeTests(unittest.TestCase):
    def fixture(self, status="claimed"):
        config = json.loads(Path("config.example.json").read_text())
        config["mode"] = "active"
        state = {
            "schema_version": 2,
            "checks": [],
            "executions": [{
                "proposal_issue": 8, "revision": "b" * 64,
                "comment_id": 1, "status": status,
            }],
        }
        return Mock(), config, state

    def finish(self, api, config, status):
        return finish_execution(
            api, config, 7, 8, "b" * 64, 1, status
        )

    def test_claimed_execution_can_record_each_terminal_outcome(self):
        for status in ("succeeded", "failed", "uncertain"):
            api, config, state = self.fixture()
            with (
                patch("execution.load_state", return_value=state),
                patch("execution.save_state") as saver,
            ):
                self.finish(api, config, status)
            saved = saver.call_args.args[3]
            self.assertEqual(saved["executions"][0]["status"], status)
            self.assertEqual(state["executions"][0]["status"], "claimed")

    def test_repeating_same_outcome_does_not_write_again(self):
        api, config, state = self.fixture("succeeded")
        with (
            patch("execution.load_state", return_value=state),
            patch("execution.save_state") as saver,
        ):
            self.finish(api, config, "succeeded")
        saver.assert_not_called()

    def test_final_outcome_cannot_be_changed(self):
        api, config, state = self.fixture("failed")
        with (
            patch("execution.load_state", return_value=state),
            patch("execution.save_state") as saver,
        ):
            with self.assertRaises(ValueError):
                self.finish(api, config, "succeeded")
        saver.assert_not_called()

    def test_outcome_must_match_exact_claim(self):
        for number, revision, comment_id in (
            (9, "b" * 64, 1),
            (8, "c" * 64, 1),
            (8, "b" * 64, 2),
        ):
            api, config, state = self.fixture()
            with (
                patch("execution.load_state", return_value=state),
                patch("execution.save_state") as saver,
            ):
                with self.assertRaises(ValueError):
                    finish_execution(
                        api, config, 7, number, revision,
                        comment_id, "succeeded",
                    )
            saver.assert_not_called()

    def test_unconfirmed_outcome_does_not_change_loaded_state(self):
        api, config, state = self.fixture()
        with (
            patch("execution.load_state", return_value=state),
            patch("execution.save_state", side_effect=StateError),
        ):
            with self.assertRaises(StateError):
                self.finish(api, config, "succeeded")
        self.assertEqual(state["executions"][0]["status"], "claimed")
