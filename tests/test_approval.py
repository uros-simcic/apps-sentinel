import unittest

from approval import MAX_REPLY_CHARS, classify_reply


class ReplyClassificationTests(unittest.TestCase):
    OWNER = 12345

    def classify(self, text):
        return classify_reply(text, self.OWNER, self.OWNER)

    def test_exact_approval_accepts_case_and_surrounding_whitespace(self):
        for text in ("Approve", "approve", " APPROVE\n"):
            with self.subTest(text=text):
                self.assertEqual(self.classify(text), "approve")

    def test_exact_rejection(self):
        self.assertEqual(self.classify(" Reject "), "reject")

    def test_non_owner_cannot_approve_or_request_revision(self):
        for text in ("Approve", "Reject", "Change the timeout"):
            with self.subTest(text=text):
                self.assertIsNone(classify_reply(text, 99999, self.OWNER))

    def test_sentences_and_ambiguous_commands_are_feedback(self):
        for text in (
            "I do not approve",
            "I approve this",
            "Approve, but change the timeout",
            "Approve!",
            "Approve\nReject",
            "Keep the existing dependency",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.classify(text), "feedback")

    def test_empty_or_oversized_input_is_ignored(self):
        for text in ("", " \n\t", "x" * (MAX_REPLY_CHARS + 1)):
            with self.subTest(length=len(text)):
                self.assertIsNone(self.classify(text))
        self.assertEqual(self.classify("x" * MAX_REPLY_CHARS), "feedback")

    def test_non_string_body_is_ignored(self):
        for body in (None, 1, [], {}):
            with self.subTest(body=body):
                self.assertIsNone(classify_reply(body, self.OWNER, self.OWNER))

    def test_invalid_identity_types_and_values_are_ignored(self):
        for actor, owner in (
            (True, True),
            ("12345", self.OWNER),
            (self.OWNER, "12345"),
            (0, 0),
            (-1, -1),
        ):
            with self.subTest(actor=actor, owner=owner):
                self.assertIsNone(classify_reply("Approve", actor, owner))


if __name__ == "__main__":
    unittest.main()
