import unittest

from proposals import make_proposal, validate_proposal


class ProposalTests(unittest.TestCase):
    def fixture(self):
        return {
            "repo": "example-owner/example-app",
            "base_sha": "a" * 40,
            "summary": "Handle missing input",
            "explanation": "Return an empty result for missing input.",
            "diff": (
                "--- a/app.py\n+++ b/app.py\n"
                "@@ -1 +1 @@\n-old\n+new\n"
            ),
        }

    def test_revision_is_stable_across_dictionary_order(self):
        record = self.fixture()
        reordered = dict(reversed(list(record.items())))
        self.assertEqual(
            make_proposal(record), make_proposal(reordered)
        )

    def test_changed_contents_require_new_revision(self):
        original = make_proposal(self.fixture())
        for change in (
            {"base_sha": "b" * 40},
            {"diff": self.fixture()["diff"] + "+another line\n"},
            {"explanation": "A different explanation."},
        ):
            with self.subTest(change=change):
                revised = make_proposal({**self.fixture(), **change})
                self.assertNotEqual(
                    original["revision"], revised["revision"]
                )

    def test_changed_record_cannot_keep_old_revision(self):
        proposal = make_proposal(self.fixture())
        self.assertEqual(validate_proposal(proposal), proposal)
        proposal["diff"] += "+unapproved change\n"
        with self.assertRaises(ValueError):
            validate_proposal(proposal)

    def test_invalid_or_oversized_records_are_rejected(self):
        for change in (
            {"repo": "../other"},
            {"base_sha": "main"},
            {"summary": "x" * 161},
            {"diff": ""},
            {"diff": "x" * 50001},
        ):
            with self.subTest(change=change):
                with self.assertRaises(ValueError):
                    make_proposal({**self.fixture(), **change})
