import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from github_client import APIError, GitHub, MAX_RESPONSE_BYTES


def response(data, link=""):
    result = MagicMock()
    result.__enter__.return_value = result
    result.read.return_value = json.dumps(data).encode()
    result.headers = {"Link": link}
    return result


class GitHubClientTests(unittest.TestCase):
    def setUp(self):
        factory = patch("github_client.build_opener")
        self.addCleanup(factory.stop)
        self.opener = factory.start().return_value
        self.api = GitHub("fixture-token")

    def test_get_uses_fixed_host_and_timeout(self):
        result = response({"id": 12345})
        self.opener.open.return_value = result
        self.assertEqual(self.api.get("/user"), {"id": 12345})
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.github.com/user")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(self.opener.open.call_args.kwargs["timeout"], 15)
        result.read.assert_called_once_with(MAX_RESPONSE_BYTES + 1)

    def test_unsafe_paths_are_rejected_before_network(self):
        for path in ("https://other.example/", "//other.example/", "/x\n"):
            with self.subTest(path=path), self.assertRaises(APIError):
                self.api.get(path)
        self.opener.open.assert_not_called()

    def test_http_failure_preserves_status(self):
        self.opener.open.side_effect = HTTPError(
            "https://api.github.com/user", 403, "Forbidden", {}, None
        )
        with self.assertRaises(APIError) as caught:
            self.api.get("/user")
        self.assertEqual(caught.exception.status, 403)

    def test_oversized_and_invalid_json_fail(self):
        for raw in (b"invalid", b" " * (MAX_RESPONSE_BYTES + 1)):
            result = response({})
            result.read.return_value = raw
            self.opener.open.return_value = result
            with self.subTest(size=len(raw)), self.assertRaises(APIError):
                self.api.get("/user")

    def test_pages_collect_all_results(self):
        self.opener.open.side_effect = [
            response([1], '<https://api.github.com/items?page=2>; rel="next"'),
            response([2]),
        ]
        self.assertEqual(self.api.pages("/items"), [1, 2])

    def test_cross_host_pagination_is_rejected(self):
        self.opener.open.return_value = response(
            [1], '<https://other.example/items>; rel="next"'
        )
        with self.assertRaises(APIError):
            self.api.pages("/items")
        self.assertEqual(self.opener.open.call_count, 1)

    def test_pagination_limit_fails_instead_of_truncating(self):
        self.opener.open.return_value = response(
            [1], '<https://api.github.com/items?page=2>; rel="next"'
        )
        with self.assertRaises(APIError):
            self.api.pages("/items")
        self.assertEqual(self.opener.open.call_count, 20)
