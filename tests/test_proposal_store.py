import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from proposal_page import parse_proposal
from proposal_store import publish_proposal
from proposals import make_proposal


class ProposalStoreTests(unittest.TestCase):
    def fixture(self):
        config = json.loads(Path("config.example.json").read_text())
        config["mode"] = "active"
        owner = {"id": config["owner_id"], "login": config["owner_login"]}
        control = "/repos/" + config["control_repo"]
        target = config["apps"][0]["repo"]
        responses = {
            "/user": owner,
            control: {
                "private": True, "owner": owner.copy(),
                "full_name": config["control_repo"],
            },
            control + "/issues/7": {
                "number": 7, "state": "open", "user": owner.copy(),
                "body": '{"schema_version":1,"checks":[]}',
            },
            "/repos/" + target: {"default_branch": "main"},
            "/repos/" + target + "/commits/main": {"sha": "a" * 40},
        }
        proposal = make_proposal({
            "repo": target,
            "base_sha": "a" * 40,
            "summary": "Handle missing input",
            "explanation": "Return an empty result for missing input.",
            "diff": "-old\n+new\n",
        })
        api = Mock()
        api.get.side_effect = responses.__getitem__
        api.create_issue.side_effect = lambda path, title, body: {
            "number": 8, "state": "open", "user": owner.copy(),
            "title": title, "body": body,
            "html_url": (
                "https://github.com/" + config["control_repo"] + "/issues/8"
            ),
        }
        return api, config, proposal, responses

    def test_publishes_exact_proposal_under_owner_identity(self):
        api, config, proposal, _ = self.fixture()
        result = publish_proposal(api, config, 7, proposal)
        path, _, body = api.create_issue.call_args.args
        self.assertEqual(
            path, "/repos/" + config["control_repo"] + "/issues"
        )
        self.assertEqual(parse_proposal(body), proposal)
        self.assertEqual(result["number"], 8)
        self.assertEqual(result["revision"], proposal["revision"])
        api.create_issue.assert_called_once()

    def test_preview_and_unmonitored_targets_stop_before_network(self):
        for case in ("preview", "unmonitored"):
            api, config, proposal, _ = self.fixture()
            if case == "preview":
                config["mode"] = "preview"
            else:
                record = {
                    key: value for key, value in proposal.items()
                    if key != "revision"
                }
                record["repo"] = "example-owner/unmonitored"
                proposal = make_proposal(record)
            with self.subTest(case=case), self.assertRaises(ValueError):
                publish_proposal(api, config, 7, proposal)
            api.get.assert_not_called()
            api.create_issue.assert_not_called()

    def test_identity_privacy_and_stale_base_block_publication(self):
        for case in ("identity", "privacy", "base"):
            api, config, proposal, responses = self.fixture()
            control = "/repos/" + config["control_repo"]
            if case == "identity":
                responses["/user"]["id"] = 99999
            elif case == "privacy":
                responses[control]["private"] = False
            else:
                responses[
                    "/repos/" + proposal["repo"] + "/commits/main"
                ]["sha"] = "b" * 40
            with self.subTest(case=case), self.assertRaises(ValueError):
                publish_proposal(api, config, 7, proposal)
            api.create_issue.assert_not_called()

    def test_unconfirmed_creation_is_not_retried(self):
        api, config, proposal, _ = self.fixture()
        api.create_issue.side_effect = None
        api.create_issue.return_value = {}
        with self.assertRaises(ValueError):
            publish_proposal(api, config, 7, proposal)
        api.create_issue.assert_called_once()
