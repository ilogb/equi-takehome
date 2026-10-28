"""Where documents come from. Task 11 extends this with listing and change detection."""

from typing import Protocol


class DocumentSource(Protocol):
    def download(self, file_id: str) -> bytes: ...
