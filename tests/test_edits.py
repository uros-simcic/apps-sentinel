import hashlib
import unittest

from edits import build_edit


class EditTests(unittest.TestCase):
    def build(self, source="value = 1\n", old="1", new="2"):
        return build_edit("app.py", source, old, new, {"app.py"})

    def test_builds_exact_candidate_and_reviewable_diff(self):
        result = self.build()
        self.assertEqual(result["candidate"], "value = 2\n")
        self.assertEqual(result["base_sha256"], hashlib.sha256(
            b"value = 1\n"
        ).hexdigest())
        self.assertTrue(result["diff"].startswith(
            "--- a/app.py\n+++ b/app.py\n"
        ))
        self.assertIn("-value = 1\n+value = 2\n", result["diff"])

    def test_missing_ambiguous_and_unchanged_edits_are_rejected(self):
        for source, old, new in (
            ("value = 1\n", "missing", "2"),
            ("aaa\n", "aa", "b"),
            ("value = 1\n", "1", "1"),
            ("value = 1\n", "", "2"),
        ):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.build(source, old, new)

    def test_unsafe_paths_are_rejected_even_if_listed(self):
        for path in (
            "../app.py", "/app.py", "src/../app.py",
            ".env", ".github/workflows/run.yml", "src//app.py",
        ):
            with self.subTest(path=path), self.assertRaises(ValueError):
                build_edit(path, "old\n", "old", "new", {path})

    def test_unlisted_path_is_rejected(self):
        with self.assertRaises(ValueError):
            build_edit("other.py", "old\n", "old", "new", {"app.py"})

    def test_unsupported_text_formats_are_rejected(self):
        for source in ("value = 1", "value = 1\r\n", "value = 1\x00\n"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.build(source)

    def test_file_and_candidate_size_limits_are_enforced(self):
        for source, old, new in (
            ("old\n" + "x" * 65536 + "\n", "old", "new"),
            ("old\n", "old", "x" * 65536),
        ):
            with self.subTest(size=len(source)), self.assertRaises(ValueError):
                self.build(source, old, new)

    def test_large_diff_is_rejected_without_truncation(self):
        source = "a" * 21000 + "\n"
        with self.assertRaises(ValueError):
            self.build(source, source, "b" * 21000 + "\n")
