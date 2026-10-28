"""Where documents come from: the DocumentSource protocol, its value types and errors."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Protocol

FOLDER_MIME = "application/vnd.google-apps.folder"


@dataclass(frozen=True)
class RemoteFile:
    id: str
    name: str
    mime_type: str
    parents: list[str] = field(default_factory=list)
    trashed: bool = False

    @property
    def is_folder(self) -> bool:
        return self.mime_type == FOLDER_MIME


@dataclass(frozen=True)
class RemoteChange:
    file_id: str
    removed: bool
    file: RemoteFile | None


class SourceError(Exception):
    """A source call failed. `retryable` tells the job queue whether to back off or fail now."""

    def __init__(self, message: str, *, retryable: bool = True, status: int | None = None):
        super().__init__(message)
        self.retryable = retryable
        self.status = status


# Every ReconnectRequired message ends with this; a file failed with it is re-queued on sign-in.
RECONNECT_MARKER = "reconnect required"


class ReconnectRequired(SourceError):
    """The stored Google grant is gone (invalid_grant): the user must sign in again."""

    def __init__(self, message: str = f"Google access was revoked or expired; {RECONNECT_MARKER}"):
        super().__init__(message, retryable=False, status=401)


class PageTokenExpired(SourceError):
    """changes.list answered 410: the saved page token is no longer valid."""

    def __init__(self, message: str = "change page token expired"):
        super().__init__(message, retryable=True, status=410)


class DocumentSource(Protocol):
    def get_folder(self, folder_id: str) -> RemoteFile: ...

    def list_children(self, folder_id: str) -> list[RemoteFile]: ...

    def start_page_token(self) -> str: ...

    def list_changes(self, token: str) -> tuple[list[RemoteChange], str]: ...

    def download(self, file_id: str) -> bytes: ...

    def stream(self, file_id: str) -> Iterator[bytes]: ...

    def search_folders(self, q: str) -> list[RemoteFile]: ...
