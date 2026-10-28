"""Test doubles shared by unit tests."""

from collections.abc import Iterator
from pathlib import Path

from app.sources.base import FOLDER_MIME, PageTokenExpired, RemoteChange, RemoteFile, SourceError

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"


def folder(id: str, name: str, parent: str | None = None) -> RemoteFile:
    return RemoteFile(id=id, name=name, mime_type=FOLDER_MIME, parents=[parent] if parent else [])


def file(id: str, name: str, parent: str, mime: str = "application/pdf", trashed: bool = False) -> RemoteFile:
    return RemoteFile(id=id, name=name, mime_type=mime, parents=[parent], trashed=trashed)


class FakeDriveSource:
    """In-memory Drive.

    Bytes come from ``fixtures/`` (searched recursively by file name) or ``extra``.
    The folder tree is ``items``; ``push_change`` adds/updates an item and queues the
    change for the next ``list_changes``. Every call is recorded in ``calls``.
    """

    def __init__(
        self,
        extra: dict[str, bytes] | None = None,
        items: list[RemoteFile] | None = None,
        token: int = 100,
    ):
        self.extra = extra or {}
        self.downloads: list[str] = []
        self.items: dict[str, RemoteFile] = {f.id: f for f in items or []}
        self.pending: list[RemoteChange] = []
        self.token = token
        self.expired_tokens: set[str] = set()
        self.calls: list[str] = []

    # --- test helpers -------------------------------------------------------
    def push_change(self, item: RemoteFile | None = None, *, removed_id: str | None = None) -> None:
        if removed_id is not None:
            self.items.pop(removed_id, None)
            self.pending.append(RemoteChange(file_id=removed_id, removed=True, file=None))
            return
        assert item is not None
        if not item.trashed:
            self.items[item.id] = item
        else:
            self.items.pop(item.id, None)
        self.pending.append(RemoteChange(file_id=item.id, removed=False, file=item))

    # --- DocumentSource -----------------------------------------------------
    def get_folder(self, folder_id: str) -> RemoteFile:
        self.calls.append("get_folder")
        if folder_id not in self.items:
            raise SourceError("Drive HTTP 404: File not found", retryable=False, status=404)
        return self.items[folder_id]

    def list_children(self, folder_id: str) -> list[RemoteFile]:
        self.calls.append("list_children")
        return [f for f in self.items.values() if folder_id in f.parents and not f.trashed]

    def start_page_token(self) -> str:
        self.calls.append("start_page_token")
        return str(self.token)

    def list_changes(self, token: str) -> tuple[list[RemoteChange], str]:
        self.calls.append("list_changes")
        if token in self.expired_tokens:
            raise PageTokenExpired("page token expired")
        changes, self.pending = self.pending, []
        self.token += 3  # Drive skips token values; callers must use the returned one.
        return changes, str(self.token)

    def search_folders(self, q: str) -> list[RemoteFile]:
        self.calls.append("search_folders")
        return [
            f
            for f in self.items.values()
            if f.mime_type == FOLDER_MIME and q.lower() in f.name.lower() and not f.trashed
        ]

    def download(self, file_id: str) -> bytes:
        self.downloads.append(file_id)
        if file_id in self.extra:
            return self.extra[file_id]
        for path in FIXTURES.rglob(file_id):
            return path.read_bytes()
        raise FileNotFoundError(file_id)

    def stream(self, file_id: str) -> Iterator[bytes]:
        yield self.download(file_id)
