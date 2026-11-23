import hashlib
import unittest
from unittest.mock import Mock

import test_proposal_store
import test_sources
from delivery import deliver_proposal
from execution import claim_execution
from proposal_store import publish_proposal
from sources import prepare_repair
from state import load_state


class RepairFlowTests(unittest.TestCase):
    def test_scoped_patch_email_and_approval_share_one_revision(self):
        api, config, _, responses = test_proposal_store.ProposalStoreTests().fixture()
        _, _, repo, source_responses = test_sources.SourceTests().fixture()
        responses.update(source_responses)
        create_issue = api.create_issue.side_effect

        def create(path, title, body):
            issue = create_issue(path, title, body)
            responses[f"{path}/{issue['number']}"] = issue
            return issue

        def update(path, body):
            responses[path] = {**responses[path], "body": body}
            return responses[path]

        api.create_issue.side_effect = create
        api.update_issue_body.side_effect = update
        scope = {
            "operation": "test_only",
            "base_branch": "main",
            "test_profile": "example-checks",
            "test_profile_sha256": "b" * 64,
        }
        proposal = prepare_repair(
            api, config, repo, "a" * 40, ["app.py"], ["app.py"],
            {
                "summary": "Replace old fallback",
                "explanation": "Use the new fallback.",
                "edits": [{
                    "path": "app.py",
                    "base_sha256": hashlib.sha256(b"old\n").hexdigest(),
                    "old_text": "old\n",
                    "new_text": "new\n",
                }],
            },
            scope=scope,
        )
        published = publish_proposal(api, config, 7, proposal)
        number, revision = published["number"], published["revision"]
        send = Mock(return_value=None)
        for _ in range(2):
            result = deliver_proposal(
                api, config, 7, number, revision,
                "sender@example.com", "owner@example.com", send,
            )
            self.assertEqual(result, "sent")
        self.assertEqual(send.call_count, 1)
        body = send.call_args.args[0].get_content()
        for displayed in (published["url"], revision, proposal["diff"]):
            self.assertIn(displayed, body)

        api.pages.return_value = [{
            "id": 123,
            "user": responses["/user"],
            "body": "Approve",
            "created_at": "2026-11-22T12:00:00Z",
            "updated_at": "2026-11-22T12:00:00Z",
        }]
        claimed = claim_execution(api, config, 7, number, revision)
        self.assertEqual(claimed, {"proposal": proposal, "comment_id": 123})
        receipt, = load_state(api, config, 7)["executions"]
        self.assertEqual(receipt["revision"], revision)
        self.assertEqual(receipt["status"], "claimed")
