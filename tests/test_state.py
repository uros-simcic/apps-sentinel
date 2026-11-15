import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from state import StateError, load_state, save_state


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

    def test_loads_explicit_private_state_issue(self):
        api, config, _, _, _, state = self.fixture()
        self.assertEqual(load_state(api, config, 7), state)
        api.update_issue_body.assert_not_called()

    def test_saves_only_selected_issue_body(self):
        api, config, _, _, _, state = self.fixture()
        state["checks"] = [{"status": "fail", "incident_id": "a" * 64}]
        save_state(api, config, 7, state)
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
                save_state(api, config, 7, state)
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
                save_state(api, config, 7, state)
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
                save_state(api, config, 7, state)
            api.update_issue_body.assert_not_called()

    def test_rejects_unconfirmed_save(self):
        api, config, _, _, _, state = self.fixture()
        api.update_issue_body.side_effect = None
        api.update_issue_body.return_value = {"number": 7, "body": "different"}
        with self.assertRaises(StateError):
            save_state(api, config, 7, state)
