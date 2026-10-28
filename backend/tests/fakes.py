"""Test doubles shared by unit tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "fixtures"


class FakeDriveSource:
    """Serves bytes from ``fixtures/`` (searched recursively by file name), or from ``extra``."""

    def __init__(self, extra: dict[str, bytes] | None = None):
        self.extra = extra or {}
        self.downloads: list[str] = []

    def download(self, file_id: str) -> bytes:
        self.downloads.append(file_id)
        if file_id in self.extra:
            return self.extra[file_id]
        for path in FIXTURES.rglob(file_id):
            return path.read_bytes()
        raise FileNotFoundError(file_id)
