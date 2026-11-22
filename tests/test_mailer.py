import json
from pathlib import Path
import unittest

from mailer import build_proposal_email
from proposals import make_proposal


class MailerTests(unittest.TestCase):
    def fixture(self, **changes):
        config = json.loads(Path("config.example.json").read_text())
        proposal = make_proposal({
            "repo": config["apps"][0]["repo"],
            "base_sha": "a" * 40,
            "summary": "Handle missing input",
            "explanation": "Return an empty result for missing input.",
            "diff": (
                "--- a/app.py\n+++ b/app.py\n"
                "@@ -1 +1 @@\n-old\n+new\n"
            ),
            **changes,
        })
        url = (
            "https://github.com/" + config["control_repo"] + "/issues/17"
        )
        return config, proposal, url

    def build(self, **changes):
        config, proposal, url = self.fixture(**changes)
        return build_proposal_email(
            config, proposal, url,
            "sender@example.com", "owner@example.com",
        )

    def test_complete_patch_and_review_instructions_are_present(self):
        message = self.build()
        _, proposal, url = self.fixture()
        body = message.get_content()
        self.assertIn(proposal["diff"], body)
        self.assertIn(proposal["explanation"], body)
        self.assertIn(proposal["revision"], body)
        self.assertIn(url, body)
        self.assertIn("Approve, Reject, or feedback", body)
        self.assertIn("has not been executed", body)
        self.assertIn("Replies to this email are not read.", body)
        self.assertEqual(message.get_content_type(), "text/plain")
        self.assertIn(proposal["repo"], str(message["Subject"]))
        message.as_bytes()

    def test_subject_newlines_cannot_add_headers(self):
        message = self.build(summary="Fix input\nBcc: other@example.com")
        self.assertIsNone(message["Bcc"])
        self.assertNotIn("\n", str(message["Subject"]))

    def test_recipient_header_injection_is_rejected(self):
        config, proposal, url = self.fixture()
        with self.assertRaises(ValueError):
            build_proposal_email(
                config, proposal, url, "sender@example.com",
                "owner@example.com\r\nBcc: other@example.com",
            )

    def test_external_or_wrong_repository_links_are_rejected(self):
        config, proposal, url = self.fixture()
        for invalid in (
            "https://example.com/approve",
            url.replace("/issues/", "/pull/"),
            url + "?redirect=elsewhere",
            url.replace("/17", "/0"),
        ):
            with self.subTest(url=invalid), self.assertRaises(ValueError):
                build_proposal_email(
                    config, proposal, invalid,
                    "sender@example.com", "owner@example.com",
                )

    def test_changed_proposal_is_rejected(self):
        config, proposal, url = self.fixture()
        proposal["diff"] += "+unapproved\n"
        with self.assertRaises(ValueError):
            build_proposal_email(
                config, proposal, url,
                "sender@example.com", "owner@example.com",
            )
