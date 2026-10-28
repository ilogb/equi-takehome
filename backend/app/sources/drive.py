"""Google Drive v3 over google-auth's AuthorizedSession (the calls proven by the spike, §C)."""

import random
import time
from collections.abc import Callable, Iterator
from typing import Any

import requests
from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import AuthorizedSession

from app.sources.base import (
    FOLDER_MIME,
    PageTokenExpired,
    ReconnectRequired,
    RemoteChange,
    RemoteFile,
    SourceError,
)

API = "https://www.googleapis.com/drive/v3"
FILE_FIELDS = "id,name,mimeType,parents,trashed"
ALL_DRIVES = {"supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}
CHANGE_FIELDS = (
    "nextPageToken,newStartPageToken,"
    "changes(changeType,fileId,removed,time,file(id,name,mimeType,md5Checksum,trashed,parents))"
)
RATE_LIMIT_REASONS = {"rateLimitExceeded", "userRateLimitExceeded"}
ATTEMPTS = 4  # in-process retries for 403-rate-limit/429/5xx/network before handing back to the queue
TIMEOUT = 60


def is_invalid_grant(err: RefreshError) -> bool:
    if any(isinstance(a, dict) and a.get("error") == "invalid_grant" for a in err.args):
        return True
    return "invalid_grant" in str(err)


def refresh_error(err: RefreshError) -> SourceError:
    if is_invalid_grant(err):
        return ReconnectRequired()
    return SourceError("Google token refresh failed", retryable=True, status=401)


def _reasons(body: dict) -> set[str]:
    err = body.get("error")
    if not isinstance(err, dict):
        return set()
    return {e.get("reason", "") for e in err.get("errors") or [] if isinstance(e, dict)}


def error_for(status: int, body: dict) -> SourceError:
    """Map a Drive error response to a SourceError with the right `retryable` flag."""
    if status == 410:
        return PageTokenExpired()
    err = body.get("error")
    message = err.get("message") if isinstance(err, dict) else None
    text = f"Drive HTTP {status}" + (f": {message}" if message else "")
    retryable = status == 429 or status >= 500 or (status == 403 and bool(_reasons(body) & RATE_LIMIT_REASONS))
    return SourceError(text, retryable=retryable, status=status)


def _remote(d: dict) -> RemoteFile:
    return RemoteFile(
        id=d["id"],
        name=d.get("name", ""),
        mime_type=d.get("mimeType", ""),
        parents=list(d.get("parents") or []),
        trashed=bool(d.get("trashed", False)),
    )


def _quote(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


class GoogleDriveSource:
    """DocumentSource for one user's Drive. Pass `http` and `sleep` only in tests."""

    def __init__(self, credentials, http: Any = None, sleep: Callable[[float], None] = time.sleep):
        self.http = http if http is not None else AuthorizedSession(credentials)
        self.sleep = sleep

    def _get(self, path: str, params: dict, stream: bool = False):
        last: SourceError | None = None
        for attempt in range(ATTEMPTS):
            if attempt:
                self.sleep(min(2**attempt, 32) + random.random())
            try:
                resp = self.http.get(f"{API}{path}", params=params, stream=stream, timeout=TIMEOUT)
            except RefreshError as err:
                raise refresh_error(err) from None
            except (requests.RequestException, TransportError) as err:
                last = SourceError(f"Drive unreachable: {type(err).__name__}", retryable=True)
                continue
            if resp.status_code < 400:
                return resp
            try:
                body = resp.json()
            except ValueError:
                body = {}
            resp.close()
            last = error_for(resp.status_code, body if isinstance(body, dict) else {})
            if not last.retryable or isinstance(last, PageTokenExpired):
                raise last
        assert last is not None
        raise last

    def _json(self, path: str, params: dict) -> dict:
        return self._get(path, params).json()

    def get_folder(self, folder_id: str) -> RemoteFile:
        return _remote(self._json(f"/files/{folder_id}", {"fields": FILE_FIELDS, "supportsAllDrives": "true"}))

    def _list(self, q: str, page_size: int = 1000, max_pages: int | None = None) -> list[RemoteFile]:
        out: list[RemoteFile] = []
        page: str | None = None
        pages = 0
        while True:
            params = {"q": q, "pageSize": page_size, "fields": f"nextPageToken,files({FILE_FIELDS})", **ALL_DRIVES}
            if page:
                params["pageToken"] = page
            data = self._json("/files", params)
            out += [_remote(f) for f in data.get("files", [])]
            page = data.get("nextPageToken")
            pages += 1
            if not page or (max_pages is not None and pages >= max_pages):
                return out

    def list_children(self, folder_id: str) -> list[RemoteFile]:
        return self._list(f"'{_quote(folder_id)}' in parents and trashed=false")

    def search_folders(self, q: str) -> list[RemoteFile]:
        query = f"mimeType='{FOLDER_MIME}' and trashed=false"
        if q.strip():
            query += f" and name contains '{_quote(q.strip())}'"
        return self._list(query, page_size=50, max_pages=1)

    def start_page_token(self) -> str:
        return self._json("/changes/startPageToken", {"supportsAllDrives": "true"})["startPageToken"]

    def list_changes(self, token: str) -> tuple[list[RemoteChange], str]:
        changes: list[RemoteChange] = []
        while True:
            params = {
                "pageToken": token,
                "pageSize": 1000,
                "includeRemoved": "true",
                "fields": CHANGE_FIELDS,
                **ALL_DRIVES,
            }
            data = self._json("/changes", params)
            for c in data.get("changes", []):
                file_id = c.get("fileId")
                if not file_id:  # e.g. changeType "drive": a shared-drive change, not a file
                    continue
                f = c.get("file")
                changes.append(
                    RemoteChange(file_id=file_id, removed=bool(c.get("removed")), file=_remote(f) if f else None)
                )
            if "nextPageToken" in data:
                token = data["nextPageToken"]
            else:
                return changes, data["newStartPageToken"]

    def stream(self, file_id: str) -> Iterator[bytes]:
        resp = self._get(f"/files/{file_id}", {"alt": "media", "supportsAllDrives": "true"}, stream=True)
        try:
            yield from resp.iter_content(65536)
        except requests.RequestException as err:
            raise SourceError(f"Drive download interrupted: {type(err).__name__}", retryable=True) from None
        finally:
            resp.close()

    def download(self, file_id: str) -> bytes:
        return b"".join(self.stream(file_id))
