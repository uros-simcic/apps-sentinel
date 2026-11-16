import hashlib
import unittest

from edits import build_edit, build_edits


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


class BatchEditTests(unittest.TestCase):
    def edit(self, path, source, replacement):
        return {
            "path": path,
            "base_sha256": hashlib.sha256(source.encode()).hexdigest(),
            "old_text": source,
            "new_text": replacement,
        }

    def test_combines_exact_candidates_without_changing_sources(self):
        sources = {"a.py": "old_a\n", "b.py": "old_b\n"}
        result = build_edits([
            self.edit("a.py", sources["a.py"], "new_a\n"),
            self.edit("b.py", sources["b.py"], "new_b\n"),
        ], sources, set(sources))
        self.assertEqual(
            [edit["candidate"] for edit in result["edits"]],
            ["new_a\n", "new_b\n"],
        )
        self.assertEqual(
            result["diff"],
            "".join(edit["diff"] for edit in result["edits"]),
        )
        self.assertEqual(sources, {"a.py": "old_a\n", "b.py": "old_b\n"})

    def test_stale_source_fingerprint_is_rejected(self):
        edit = self.edit("a.py", "old\n", "new\n")
        edit["base_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            build_edits([edit], {"a.py": "old\n"}, {"a.py"})

    def test_duplicate_paths_and_extra_fields_are_rejected(self):
        edit = self.edit("a.py", "old\n", "new\n")
        for records in (
            [edit, edit],
            [{**edit, "command": "unapproved command"}],
        ):
            with self.subTest(records=records), self.assertRaises(ValueError):
                build_edits(records, {"a.py": "old\n"}, {"a.py"})

    def test_file_count_limit_is_enforced(self):
        sources = {f"file{i}.py": "old\n" for i in range(6)}
        records = [
            self.edit(path, source, "new\n")
            for path, source in sources.items()
        ]
        with self.assertRaises(ValueError):
            build_edits(records, sources, set(sources))

    def test_changed_line_limit_is_enforced(self):
        source = "old\n" * 201
        with self.assertRaises(ValueError):
            build_edits(
                [self.edit("a.py", source, "new\n" * 201)],
                {"a.py": source}, {"a.py"},
            )

    def test_combined_diff_limit_is_enforced(self):
        source = "a" * 11000 + "\n"
        sources = {"a.py": source, "b.py": source}
        records = [
            self.edit(path, source, "b" * 11000 + "\n")
            for path in sources
        ]
        with self.assertRaises(ValueError):
            build_edits(records, sources, set(sources))
