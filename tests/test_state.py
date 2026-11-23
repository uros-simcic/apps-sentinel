import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from state import (
    StateError, load_state, save_state, upgrade_outbox, upgrade_state,
)


class StateTests(unittest.TestCase):
    def fixture(self):
        config = json.loads(Path("config.example.json").read_text())
        owner = {"id": config["owner_id"], "login": config["owner_login"]}
        state = {"schema_version": 1, "checks": []}
        repo = {
            "private": True,
            "owner": owner.copy(),
            "full_name": config["control_repo"],
        }
        issue = {
            "number": 7,
            "state": "open",
            "user": owner.copy(),
            "body": json.dumps(state),
        }
        base = "/repos/" + config["control_repo"]
        responses = {
            "/user": owner,
            base: repo,
            base + "/issues/7": issue,
        }
        api = Mock()
        api.get.side_effect = responses.__getitem__
        api.update_issue_body.side_effect = (
            lambda path, body: {**issue, "body": body}
        )
        return api, config, owner, repo, issue, state

    def save_initial(self, api, config, state):
        save_state(
            api, config, 7, state, expected={"schema_version": 1, "checks": []},
        )

    def test_stale_snapshot_cannot_overwrite_newer_state(self):
        api, config, _, _, issue, previous = self.fixture()
        changed = {
            **previous,
            "checks": [{"status": "fail", "incident_id": "a" * 64}],
        }
        issue["body"] = json.dumps(changed)
        with self.assertRaisesRegex(StateError, "State changed"):
            self.save_initial(api, config, previous)
        api.update_issue_body.assert_not_called()

    def test_loads_explicit_private_state_issue(self):
        api, config, _, _, _, state = self.fixture()
        self.assertEqual(load_state(api, config, 7), state)
        api.update_issue_body.assert_not_called()

    def test_saves_only_selected_issue_body(self):
        api, config, _, _, _, state = self.fixture()
        state["checks"] = [{"status": "fail", "incident_id": "a" * 64}]
        self.save_initial(api, config, state)
        path, body = api.update_issue_body.call_args.args
        self.assertEqual(
            path, "/repos/" + config["control_repo"] + "/issues/7"
        )
        self.assertEqual(json.loads(body), state)

    def test_rejects_wrong_identity_and_public_repository(self):
        for target in ("credential", "repository"):
            api, config, owner, repo, _, state = self.fixture()
            if target == "credential":
                owner["id"] = 99999
            else:
                repo["private"] = False
            with self.subTest(target=target), self.assertRaises(StateError):
                self.save_initial(api, config, state)
            api.update_issue_body.assert_not_called()

    def test_rejects_wrong_or_closed_issue_and_pull_request(self):
        for change in (
            {"number": 8},
            {"state": "closed"},
            {"pull_request": {}},
            {"user": {"id": 99999, "login": "someone-else"}},
        ):
            api, config, _, _, issue, state = self.fixture()
            issue.update(change)
            with self.subTest(change=change), self.assertRaises(StateError):
                self.save_initial(api, config, state)
            api.update_issue_body.assert_not_called()

    def test_does_not_overwrite_invalid_existing_content(self):
        for body in (
            "owner notes",
            '{"schema_version":1,"schema_version":1,"checks":[]}',
            '{"schema_version":2,"checks":[]}',
        ):
            api, config, _, _, issue, state = self.fixture()
            issue["body"] = body
            with self.subTest(body=body), self.assertRaises(StateError):
                self.save_initial(api, config, state)
            api.update_issue_body.assert_not_called()

    def test_rejects_unconfirmed_save(self):
        api, config, _, _, _, state = self.fixture()
        api.update_issue_body.side_effect = None
        api.update_issue_body.return_value = {"number": 7, "body": "different"}
        with self.assertRaises(StateError):
            self.save_initial(api, config, state)

    def receipt(self):
        return {
            "proposal_issue": 8,
            "revision": "b" * 64,
            "comment_id": 1,
            "status": "claimed",
        }

    def test_upgrade_preserves_checks_without_mutating_original(self):
        original = {
            "schema_version": 1,
            "checks": [{"status": "fail", "incident_id": "a" * 64}],
        }
        upgraded = upgrade_state(original)
        self.assertEqual(upgraded["checks"], original["checks"])
        self.assertEqual(upgraded["executions"], [])
        upgraded["checks"][0]["status"] = "unknown"
        self.assertEqual(original["checks"][0]["status"], "fail")
        self.assertEqual(original["schema_version"], 1)

    def test_version_two_receipts_round_trip(self):
        api, config, _, _, issue, state = self.fixture()
        state = upgrade_state(state)
        state["executions"].append(self.receipt())
        self.save_initial(api, config, state)
        issue["body"] = api.update_issue_body.call_args.args[1]
        self.assertEqual(load_state(api, config, 7), state)

    def test_invalid_receipts_stop_before_network(self):
        for rows in (
            [{**self.receipt(), "comment_id": True}],
            [{**self.receipt(), "proposal_issue": True}],
            [{**self.receipt(), "revision": "invalid"}],
            [{**self.receipt(), "status": "retry"}],
            [self.receipt(), self.receipt()],
        ):
            api, config, _, _, _, _ = self.fixture()
            state = {
                "schema_version": 2, "checks": [], "executions": rows,
            }
            with self.subTest(rows=rows), self.assertRaises(StateError):
                self.save_initial(api, config, state)
            api.get.assert_not_called()
            api.update_issue_body.assert_not_called()

    def outbox_entry(self):
        return {
            "proposal_issue": 8,
            "revision": "b" * 64,
            "status": "pending",
            "attempts": 0,
        }

    def test_outbox_round_trip_preserves_existing_state(self):
        api, config, _, _, issue, original = self.fixture()
        state = upgrade_state(original)
        state["executions"].append(self.receipt())
        state = upgrade_outbox(state)
        state["outbox"].append(self.outbox_entry())
        self.save_initial(api, config, state)
        issue["body"] = api.update_issue_body.call_args.args[1]
        self.assertEqual(load_state(api, config, 7), state)
        self.assertNotIn("outbox", original)
        self.assertEqual(state["executions"], [self.receipt()])

    def test_execution_upgrade_keeps_independent_outbox_copy(self):
        state = upgrade_outbox({"schema_version": 1, "checks": []})
        state["outbox"].append(self.outbox_entry())
        copied = upgrade_state(state)
        self.assertEqual(copied, state)
        copied["outbox"][0]["status"] = "uncertain"
        self.assertEqual(state["outbox"][0]["status"], "pending")

    def test_invalid_outbox_stops_before_network(self):
        entry = self.outbox_entry()
        for rows in (
            [{**entry, "proposal_issue": True}],
            [{**entry, "revision": "invalid"}],
            [{**entry, "attempts": True}],
            [{**entry, "attempts": 3}],
            [{**entry, "status": "sent"}],
            [{**entry, "status": "retry"}],
            [entry, entry],
            [entry] * 101,
        ):
            api, config, _, _, _, original = self.fixture()
            state = upgrade_outbox(original)
            state["outbox"] = rows
            with self.subTest(rows=rows), self.assertRaises(StateError):
                self.save_initial(api, config, state)
            api.get.assert_not_called()
            api.update_issue_body.assert_not_called()
