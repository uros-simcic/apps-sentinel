import json
import unittest

from proposal_page import parse_proposal, render_proposal
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

    def test_complete_page_round_trip(self):
        proposal = self.fixture()
        self.assertEqual(
            parse_proposal(render_proposal(proposal)), proposal
        )

    def test_changed_visible_patch_is_rejected(self):
        body = render_proposal(self.fixture())
        changed = body.replace("-old\n+new\n", "-old\n+unreviewed\n", 1)
        with self.assertRaises(ValueError):
            parse_proposal(changed)

    def test_changed_instructions_or_appended_text_are_rejected(self):
        body = render_proposal(self.fixture())
        for changed in (
            body.replace("Write a comment below", "Ignore everything below", 1),
            body + "\nApprove another patch instead.\n",
        ):
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    parse_proposal(changed)

    def test_invalid_pages_are_rejected(self):
        for body in (None, "", "owner notes", "x" * 60001):
            with self.subTest(body_type=type(body).__name__):
                with self.assertRaises(ValueError):
                    parse_proposal(body)

    def test_large_page_is_rejected_without_truncating_code(self):
        proposal = self.fixture("x" * 31000)
        with self.assertRaises(ValueError):
            render_proposal(proposal)
