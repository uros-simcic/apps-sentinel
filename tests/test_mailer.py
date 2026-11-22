import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from mailer import build_proposal_email, prepare_proposal_email
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

    def test_stored_proposal_has_matching_link_and_stable_identifier(self):
        config, proposal, url = self.fixture()
        api = Mock()

        def prepare(record):
            with patch("mailer.load_proposal", return_value=record) as load:
                message = prepare_proposal_email(
                    api, config, 1, 17, record["revision"],
                    "sender@example.com", "owner@example.com",
                )
            load.assert_called_once_with(
                api, config, 1, 17, record["revision"]
            )
            return message

        first = prepare(proposal)
        second = prepare(proposal)
        self.assertIn(url, first.get_content())
        self.assertIn(proposal["diff"], first.get_content())
        self.assertEqual(first["Message-ID"], second["Message-ID"])

        _, revised, _ = self.fixture(explanation="A revised solution.")
        third = prepare(revised)
        self.assertNotEqual(first["Message-ID"], third["Message-ID"])
        self.assertEqual(api.method_calls, [])

    def test_failed_proposal_verification_stops_email_construction(self):
        config, proposal, _ = self.fixture()
        with (
            patch("mailer.load_proposal", side_effect=ValueError),
            patch("mailer.build_proposal_email") as build,
        ):
            with self.assertRaises(ValueError):
                prepare_proposal_email(
                    Mock(), config, 1, 17, proposal["revision"],
                    "sender@example.com", "owner@example.com",
                )
        build.assert_not_called()
