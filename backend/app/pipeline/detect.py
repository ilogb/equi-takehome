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

_EXTENSION_KINDS: dict[str, FileKind] = {
    ".pdf": "pdf",
    ".csv": "csv",
    ".xlsx": "xlsx",
    ".html": "html",
    ".htm": "html",
    ".eml": "eml",
}

_GOOGLE_NATIVE_PREFIX = "application/vnd.google-apps."

_SCANNED_MIN_CHARS = 20


def kind_for(mime: str, name: str) -> FileKind | None:
    """Map a Drive MIME type to a kind, falling back to the file extension.

    Drive often reports a generic or wrong MIME type for uploads
    (``application/octet-stream``, ``text/plain``, ``application/vnd.ms-excel`` for a
    CSV), so an unrecognised MIME defers to the extension. Google-native documents
    (Docs, Sheets, ...) have no downloadable bytes and stay unsupported whatever
    their name.
    """
    base = mime.split(";")[0].strip().lower()
    if base.startswith(_GOOGLE_NATIVE_PREFIX):
        return None
    if kind := _MIME_KINDS.get(base):
        return kind
    dot = name.rfind(".")
    return _EXTENSION_KINDS.get(name[dot:].lower()) if dot >= 0 else None


def is_scanned(pages: list[str]) -> bool:
    """True when more than half the pages carry under 20 characters of text."""
    sparse = sum(len(page.strip()) < _SCANNED_MIN_CHARS for page in pages)
    return sparse > len(pages) / 2
