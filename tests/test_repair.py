import hashlib
import unittest
from unittest.mock import Mock, patch

from proposal_page import parse_proposal, render_proposal
from sources import prepare_repair


class RepairTests(unittest.TestCase):
    def fixture(self):
        return {
            "summary": "Handle missing input",
            "explanation": "Replace the old fallback.",
            "edits": [{
                "path": "app.py",
                "base_sha256": hashlib.sha256(b"old\n").hexdigest(),
                "old_text": "old\n",
                "new_text": "new\n",
            }],
        }

    def prepare(self, answer):
        api = Mock()
        bundle = {
            "repo": "example-owner/example-app",
            "base_sha": "a" * 40,
            "sources": {"app.py": "old\n"},
        }
        with patch("sources.read_sources", return_value=bundle) as reader:
            proposal = prepare_repair(
                api, {}, bundle["repo"], bundle["base_sha"],
                ["app.py"], {"app.py"}, answer,
            )
        reader.assert_called_once_with(
            api, {}, bundle["repo"], bundle["base_sha"],
            ["app.py"], {"app.py"},
        )
        api.assert_not_called()
        self.assertEqual(api.method_calls, [])
        return proposal

    def test_review_page_contains_the_generated_patch(self):
        proposal = self.prepare(self.fixture())
        self.assertEqual(
            proposal["diff"],
            "--- a/app.py\n+++ b/app.py\n"
            "@@ -1 +1 @@\n-old\n+new\n",
        )
        self.assertEqual(
            parse_proposal(render_proposal(proposal)), proposal
        )

    def test_stale_source_fingerprint_is_rejected(self):
        answer = self.fixture()
        answer["edits"][0]["base_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            self.prepare(answer)

    def test_extra_answer_fields_stop_before_source_access(self):
        with patch("sources.read_sources") as reader:
            with self.assertRaises(ValueError):
                prepare_repair(
                    Mock(), {}, "example-owner/example-app",
                    "a" * 40, ["app.py"], {"app.py"},
                    {**self.fixture(), "command": "unexpected"},
                )
        reader.assert_not_called()

    def test_oversized_review_page_is_rejected(self):
        answer = self.fixture()
        answer["explanation"] = "x" * 40000
        with self.assertRaises(ValueError):
            self.prepare(answer)
