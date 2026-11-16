import base64
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

from edits import build_edits
from sources import read_sources


class SourceTests(unittest.TestCase):
    def fixture(self, raw=b"old\n", paths=("app.py",)):
        config = json.loads(Path("config.example.json").read_text())
        repo = config["apps"][0]["repo"]
        base = "/repos/" + repo
        blob_sha = hashlib.sha1(
            f"blob {len(raw)}\0".encode() + raw
        ).hexdigest()
        responses = {
            "/user": {
                "id": config["owner_id"], "login": config["owner_login"],
            },
            base + "/commits/" + "a" * 40: {
                "sha": "a" * 40, "commit": {"tree": {"sha": "b" * 40}},
            },
            base + "/git/trees/" + "b" * 40 + "?recursive=1": {
                "sha": "b" * 40, "truncated": False,
                "tree": [{
                    "path": path, "type": "blob", "mode": "100644",
                    "size": len(raw), "sha": blob_sha,
                } for path in paths],
            },
            base + "/git/blobs/" + blob_sha: {
                "sha": blob_sha, "encoding": "base64", "size": len(raw),
                "content": base64.b64encode(raw).decode(),
            },
        }
        api = Mock()
        api.get.side_effect = responses.__getitem__
        return api, config, repo, responses

    def read(self, api, config, repo, paths=("app.py",)):
        return read_sources(
            api, config, repo, "a" * 40, list(paths), set(paths)
        )

    def test_pinned_source_builds_a_fingerprint_checked_repair(self):
        api, config, repo, _ = self.fixture()
        bundle = self.read(api, config, repo)
        repair = build_edits([{
            "path": "app.py",
            "base_sha256": bundle["fingerprints"]["app.py"],
            "old_text": "old\n", "new_text": "new\n",
        }], bundle["sources"], {"app.py"})
        self.assertEqual(repair["edits"][0]["candidate"], "new\n")
        api.create_issue.assert_not_called()
        api.update_issue_body.assert_not_called()

    def test_forbidden_path_stops_before_network(self):
        api, config, repo, _ = self.fixture()
        with self.assertRaises(ValueError):
            self.read(api, config, repo, (".env",))
        api.get.assert_not_called()

    def test_wrong_identity_stops_before_source_access(self):
        api, config, repo, responses = self.fixture()
        responses["/user"]["id"] = 99999
        with self.assertRaises(ValueError):
            self.read(api, config, repo)
        api.get.assert_called_once_with("/user")

    def test_symlink_submodule_and_truncated_tree_are_rejected(self):
        for case in ("120000", "160000", "truncated"):
            api, config, repo, responses = self.fixture()
            tree = responses[
                "/repos/" + repo + "/git/trees/" + "b" * 40 + "?recursive=1"
            ]
            if case == "truncated":
                tree["truncated"] = True
            else:
                tree["tree"][0]["mode"] = case
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.read(api, config, repo)
            self.assertEqual(api.get.call_count, 3)

    def test_changed_blob_bytes_are_rejected(self):
        api, config, repo, responses = self.fixture()
        blob = next(
            value for key, value in responses.items() if "/git/blobs/" in key
        )
        blob["content"] = base64.b64encode(b"bad\n").decode()
        with self.assertRaises(ValueError):
            self.read(api, config, repo)

    def test_combined_source_size_is_bounded(self):
        paths = ("a.py", "b.py")
        api, config, repo, _ = self.fixture(
            b"x" * 65535 + b"\n", paths
        )
        with self.assertRaises(ValueError):
            self.read(api, config, repo, paths)
