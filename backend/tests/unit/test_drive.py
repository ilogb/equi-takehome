"""GoogleDriveSource over a fake HTTP session (no network)."""

import pytest
import requests
from google.auth.exceptions import RefreshError

from app.sources.base import PageTokenExpired, ReconnectRequired, SourceError
from app.sources.drive import GoogleDriveSource, error_for


class Resp:
    def __init__(self, status: int, body: dict | None = None, chunks: list[bytes] | None = None):
        self.status_code = status
        self._body = body or {}
        self._chunks = chunks or []
        self.text = str(self._body)

    def json(self):
        return self._body

    def iter_content(self, size):
        yield from self._chunks

    def close(self):
        pass


class FakeHttp:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests: list[tuple[str, dict]] = []

    def get(self, url, params=None, stream=False, timeout=None):
        self.requests.append((url, dict(params or {})))
        r = self.responses.pop(0)
        if isinstance(r, BaseException):
            raise r
        return r


def source(*responses) -> tuple[GoogleDriveSource, FakeHttp]:
    http = FakeHttp(*responses)
    return GoogleDriveSource(credentials=None, http=http, sleep=lambda s: None), http


def rate_limited():
    return Resp(403, {"error": {"errors": [{"reason": "userRateLimitExceeded"}], "message": "slow down"}})


def test_error_classification():
    assert error_for(429, {}).retryable is True
    assert error_for(500, {}).retryable is True
    assert error_for(503, {}).retryable is True
    assert error_for(403, rate_limited().json()).retryable is True
    assert error_for(403, {"error": {"errors": [{"reason": "fileNotDownloadable"}]}}).retryable is False
    assert error_for(401, {}).retryable is False
    assert error_for(404, {}).retryable is False
    assert isinstance(error_for(410, {}), PageTokenExpired)


def test_retries_403_rate_limit_and_429_then_succeeds():
    src, http = source(rate_limited(), Resp(429), Resp(200, {"startPageToken": "149371"}))
    assert src.start_page_token() == "149371"
    assert len(http.requests) == 3


def test_gives_up_with_retryable_error():
    src, _ = source(*[Resp(503)] * 5)
    with pytest.raises(SourceError) as err:
        src.start_page_token()
    assert err.value.retryable is True


def test_network_error_is_retryable():
    src, _ = source(*[requests.ConnectionError("down")] * 5)
    with pytest.raises(SourceError) as err:
        src.start_page_token()
    assert err.value.retryable is True


def test_404_not_retried():
    src, http = source(Resp(404, {"error": {"message": "File not found"}}))
    with pytest.raises(SourceError) as err:
        src.get_folder("nope")
    assert err.value.retryable is False
    assert len(http.requests) == 1


def test_invalid_grant_during_request_is_reconnect():
    src, _ = source(RefreshError("invalid_grant: revoked", {"error": "invalid_grant"}))
    with pytest.raises(ReconnectRequired):
        src.start_page_token()


def test_list_children_paginates_with_query():
    src, http = source(
        Resp(200, {"files": [{"id": "a", "name": "A", "mimeType": "application/pdf", "parents": ["r"]}], "nextPageToken": "p2"}),
        Resp(200, {"files": [{"id": "b", "name": "B", "mimeType": "text/csv", "parents": ["r"]}]}),
    )
    files = src.list_children("r")
    assert [f.id for f in files] == ["a", "b"]
    assert files[0].parents == ["r"] and files[0].trashed is False
    params = http.requests[0][1]
    assert params["q"] == "'r' in parents and trashed=false"
    assert params["supportsAllDrives"] == "true" and params["includeItemsFromAllDrives"] == "true"
    assert http.requests[1][1]["pageToken"] == "p2"


def test_list_changes_mask_and_next_token():
    src, http = source(
        Resp(200, {"changes": [{"fileId": "x", "removed": True}], "nextPageToken": "150"}),
        Resp(200, {"changes": [{"fileId": "y", "removed": False, "file": {"id": "y", "name": "y.pdf", "mimeType": "application/pdf", "parents": ["r"], "trashed": False}}], "newStartPageToken": "153"}),
    )
    changes, token = src.list_changes("149")
    assert token == "153"
    assert changes[0].removed and changes[0].file is None
    assert changes[1].file.parents == ["r"]
    params = http.requests[0][1]
    assert params["includeRemoved"] == "true"
    assert "file(" in params["fields"] and "parents" in params["fields"] and "trashed" in params["fields"]
    assert http.requests[1][1]["pageToken"] == "150"


def test_list_changes_skips_entries_without_file_id():
    src, _ = source(
        Resp(200, {"changes": [{"changeType": "drive", "driveId": "d1", "removed": False},
                               {"changeType": "file", "fileId": "x", "removed": True}],
                   "newStartPageToken": "200"}),
    )
    changes, token = src.list_changes("199")
    assert token == "200"
    assert [c.file_id for c in changes] == ["x"]


def test_list_changes_410():
    src, _ = source(Resp(410, {}))
    with pytest.raises(PageTokenExpired):
        src.list_changes("1")


def test_search_folders_escapes_quotes():
    src, http = source(Resp(200, {"files": []}))
    src.search_folders("O'Brien")
    q = http.requests[0][1]["q"]
    assert "name contains 'O\\'Brien'" in q
    assert "mimeType='application/vnd.google-apps.folder'" in q


def test_download_streams_media():
    src, http = source(Resp(200, chunks=[b"ab", b"cd"]))
    assert src.download("f") == b"abcd"
    assert http.requests[0][1]["alt"] == "media"
