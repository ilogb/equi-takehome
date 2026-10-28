"""Decide how a downloaded Drive file is processed."""

from typing import Literal

FileKind = Literal["pdf", "csv", "xlsx", "html", "eml"]

_MIME_KINDS: dict[str, FileKind] = {
    "application/pdf": "pdf",
    "text/csv": "csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/html": "html",
    "message/rfc822": "eml",
}

_SCANNED_MIN_CHARS = 20


def kind_for(mime: str, name: str) -> FileKind | None:
    """Map a Drive MIME type (falling back to the file extension) to a kind."""
    kind = _MIME_KINDS.get(mime)
    if kind is None and name.lower().endswith(".eml"):
        return "eml"
    return kind


def is_scanned(pages: list[str]) -> bool:
    """True when more than half the pages carry under 20 characters of text."""
    sparse = sum(len(page.strip()) < _SCANNED_MIN_CHARS for page in pages)
    return sparse > len(pages) / 2
