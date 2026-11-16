import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from proposal_page import parse_proposal, render_proposal
from proposal_store import load_proposal, publish_proposal
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
        api.pages.return_value = []
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

    def review_fixture(self):
        api, config, proposal, responses = self.fixture()
        responses[
            "/repos/" + config["control_repo"] + "/issues/8"
        ] = self.existing_issue(config, proposal)
        return api, config, proposal, responses

    def test_loads_only_the_pinned_proposal_revision(self):
        api, config, proposal, _ = self.review_fixture()
        self.assertEqual(
            load_proposal(api, config, 7, 8, proposal["revision"]),
            proposal,
        )
        api.create_issue.assert_not_called()
        api.update_issue_body.assert_not_called()

    def test_different_revision_is_rejected(self):
        api, config, _, _ = self.review_fixture()
        with self.assertRaises(ValueError):
            load_proposal(api, config, 7, 8, "0" * 64)

    def test_changed_or_unowned_proposal_issue_is_rejected(self):
        for case in ("author", "closed", "pull_request", "patch"):
            api, config, proposal, responses = self.review_fixture()
            issue = responses[
                "/repos/" + config["control_repo"] + "/issues/8"
            ]
            if case == "author":
                issue["user"] = {"id": 99999}
            elif case == "closed":
                issue["state"] = "closed"
            elif case == "pull_request":
                issue["pull_request"] = {}
            else:
                issue["body"] = issue["body"].replace(
                    "-old\n+new\n", "-old\n+unreviewed\n", 1
                )
            with self.subTest(case=case), self.assertRaises(ValueError):
                load_proposal(api, config, 7, 8, proposal["revision"])
            api.create_issue.assert_not_called()
            api.update_issue_body.assert_not_called()

    def test_invalid_reference_stops_before_network(self):
        for number, revision in (
            (True, "a" * 64), (0, "a" * 64), (8, "unknown"),
        ):
            api, config, _, _ = self.fixture()
            with self.subTest(number=number), self.assertRaises(ValueError):
                load_proposal(api, config, 7, number, revision)
            api.get.assert_not_called()

    def existing_issue(self, config, proposal):
        return {
            "number": 8,
            "state": "open",
            "user": {"id": config["owner_id"]},
            "title": proposal["repo"] + ": Handle missing input",
            "body": render_proposal(proposal),
            "html_url": (
                "https://github.com/" + config["control_repo"] + "/issues/8"
            ),
        }

    def test_repeated_publication_reuses_existing_issue(self):
        api, config, proposal, _ = self.fixture()
        api.pages.return_value = [self.existing_issue(config, proposal)]
        result = publish_proposal(api, config, 7, proposal)
        self.assertEqual(result["number"], 8)
        self.assertEqual(result["revision"], proposal["revision"])
        api.create_issue.assert_not_called()

    def test_closed_proposal_is_not_recreated(self):
        api, config, proposal, _ = self.fixture()
        issue = self.existing_issue(config, proposal)
        issue["state"] = "closed"
        api.pages.return_value = [issue]
        with self.assertRaises(ValueError):
            publish_proposal(api, config, 7, proposal)
        api.create_issue.assert_not_called()

    def test_duplicate_matches_stop_without_creating_another(self):
        api, config, proposal, _ = self.fixture()
        issue = self.existing_issue(config, proposal)
        api.pages.return_value = [issue, {**issue, "number": 9}]
        with self.assertRaises(ValueError):
            publish_proposal(api, config, 7, proposal)
        api.create_issue.assert_not_called()

    def test_invalid_listing_stops_without_publication(self):
        for listing in (None, {}, [None]):
            api, config, proposal, _ = self.fixture()
            api.pages.return_value = listing
            with self.subTest(listing=listing), self.assertRaises(ValueError):
                publish_proposal(api, config, 7, proposal)
            api.create_issue.assert_not_called()

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
