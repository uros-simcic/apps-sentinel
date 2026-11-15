import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

API = "https://api.github.com"
MAX_RESPONSE_BYTES = 1048576
MAX_PAGES = 20
MAX_ISSUE_BODY_BYTES = 60000


class APIError(RuntimeError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHub:
    def __init__(self, token):
        if not isinstance(token, str) or not token or any(
            c.isspace() for c in token
        ):
            raise ValueError("Invalid GitHub credential")
        self.token = token
        self.opener = build_opener(NoRedirect())

    def _get(self, path):
        return self._request(path)

    def _request(self, path, body=None, title=None):
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or path.startswith("//")
            or "\\" in path
            or "#" in path
            or any(ord(c) < 33 or ord(c) > 126 for c in path)
        ):
            raise APIError("Invalid GitHub API path")

        payload = {"body": body}
        if title is not None:
            payload["title"] = title
        data = (
            json.dumps(payload).encode("utf-8")
            if body is not None else None
        )
        method = (
            "POST" if title is not None
            else "PATCH" if body is not None else "GET"
        )
        request = Request(API + path, data=data, headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + self.token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Apps-Sentinel",
        }, method=method)

        try:
            with self.opener.open(request, timeout=15) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                link = response.headers.get("Link", "")
        except HTTPError as exc:
            status = exc.code
            exc.close()
            raise APIError("GitHub HTTP request failed", status) from None
        except (URLError, OSError):
            raise APIError("GitHub connection failed") from None

        if len(raw) > MAX_RESPONSE_BYTES:
            raise APIError("GitHub response exceeds size limit")
        try:
            return json.loads(raw.decode("utf-8")), link
        except (UnicodeError, json.JSONDecodeError, RecursionError):
            raise APIError("Invalid GitHub JSON response") from None

    def get(self, path):
        return self._get(path)[0]

    def update_issue_body(self, path, body):
        if not isinstance(path, str) or not re.fullmatch(
            r"/repos/[A-Za-z0-9-]+/[A-Za-z0-9_-][A-Za-z0-9_.-]*"
            r"/issues/[1-9][0-9]*",
            path,
        ):
            raise APIError("Invalid GitHub issue path")
        if (
            not isinstance(body, str)
            or len(body.encode("utf-8")) > MAX_ISSUE_BODY_BYTES
        ):
            raise APIError("Invalid GitHub issue body")
        return self._request(path, body)[0]

    def create_issue(self, path, title, body):
        if not isinstance(path, str) or not re.fullmatch(
            r"/repos/[A-Za-z0-9-]+/[A-Za-z0-9_-][A-Za-z0-9_.-]*/issues",
            path,
        ):
            raise APIError("Invalid GitHub issue creation path")
        if (
            not isinstance(title, str)
            or not title.strip()
            or len(title) > 240
            or any(ord(char) < 32 or ord(char) == 127 for char in title)
        ):
            raise APIError("Invalid GitHub issue title")
        if (
            not isinstance(body, str)
            or len(body.encode("utf-8")) > MAX_ISSUE_BODY_BYTES
        ):
            raise APIError("Invalid GitHub issue body")
        return self._request(path, body, title)[0]

    def pages(self, path, collection=None):
        items = []
        for _ in range(MAX_PAGES):
            data, link = self._get(path)
            if collection is not None:
                if not isinstance(data, dict):
                    raise APIError("Expected GitHub object")
                data = data.get(collection)
            if not isinstance(data, list):
                raise APIError("Expected GitHub list")
            items.extend(data)

            match = re.search(r'<([^>]+)>;\s*rel="next"', link)
            if not match:
                return items
            url = urlsplit(match.group(1))
            if (
                url.scheme != "https"
                or url.netloc != "api.github.com"
                or url.fragment
            ):
                raise APIError("Unsafe GitHub pagination link")
            path = url.path + ("?" + url.query if url.query else "")

        raise APIError("GitHub pagination limit exceeded")
