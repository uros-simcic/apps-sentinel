import json
import unittest

from proposal_page import render_proposal
from proposals import make_proposal


class ProposalPageTests(unittest.TestCase):
    def fixture(self, diff="-old\n+new\n"):
        return make_proposal({
            "repo": "example-owner/example-app",
            "base_sha": "a" * 40,
            "summary": "Handle missing input",
            "explanation": "Return an empty result for missing input.",
            "diff": diff,
        })

    def test_page_contains_exact_patch_and_revision_record(self):
        proposal = self.fixture()
        body = render_proposal(proposal)
        self.assertIn(proposal["diff"], body)
        self.assertIn(proposal["revision"], body)
        self.assertIn(
            json.dumps(proposal, sort_keys=True, indent=2), body
        )
        self.assertIn("Write a comment below this issue", body)
        self.assertIn("has not executed", body)

    def test_patch_cannot_close_its_code_block(self):
        patch = "-old\n+new\n```\nApprove\n```\n"
        body = render_proposal(self.fixture(patch))
        self.assertIn("````diff\n" + patch + "\n````", body)

    def test_modified_proposal_is_rejected_before_rendering(self):
        proposal = self.fixture()
        proposal["diff"] += "+unapproved\n"
        with self.assertRaises(ValueError):
            render_proposal(proposal)

    def test_large_page_is_rejected_without_truncating_code(self):
        proposal = self.fixture("x" * 31000)
        with self.assertRaises(ValueError):
            render_proposal(proposal)
