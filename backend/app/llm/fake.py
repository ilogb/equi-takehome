"""Network-free LLMProvider that replays recorded model output."""

import hashlib
import math
from pathlib import Path

from app.llm.base import ChatTurn, LLMError
from app.models import EMBEDDING_DIMS
from app.pipeline.schema import CsvMapping, DocumentExtraction

_PREFIX = "cur_"


class FakeLLM:
    """``extract`` replays ``<file_name>.json``; ``map_table`` replays ``map_<name>.json``.

    ``chat`` pops turns from the ``chat_script`` given at construction.
    """

    def __init__(self, recorded_dir: Path | str, chat_script: list[ChatTurn] | None = None):
        self.recorded_dir = Path(recorded_dir)
        self.chat_script = list(chat_script or [])
        self.chat_calls: list[dict] = []

    def _load(self, name: str) -> str:
        for candidate in (name, _PREFIX + name):
            path = self.recorded_dir / f"{candidate}.json"
            if path.exists():
                return path.read_text()
        raise LLMError(f"no recorded response for {name}", retryable=False)

    def extract(self, *, file_name, pdf=None, text=None, known_funds=()) -> DocumentExtraction:
        return DocumentExtraction.model_validate_json(self._load(file_name))

    def map_table(self, *, name, head, tail) -> CsvMapping:
        return CsvMapping.model_validate_json(self._load(f"map_{Path(name).stem}"))

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_unit_vector(t) for t in texts]

    def chat(self, *, messages, tools) -> ChatTurn:
        self.chat_calls.append({"messages": messages, "tools": tools})
        if not self.chat_script:
            raise LLMError("chat script exhausted", retryable=False)
        return self.chat_script.pop(0)


def _unit_vector(text: str) -> list[float]:
    """Deterministic pseudo-embedding: SHA-256 expanded to EMBEDDING_DIMS, L2-normalised."""
    raw: list[float] = []
    counter = 0
    while len(raw) < EMBEDDING_DIMS:
        digest = hashlib.sha256(f"{counter}:{text}".encode()).digest()
        raw.extend(b / 127.5 - 1 for b in digest)
        counter += 1
    raw = raw[:EMBEDDING_DIMS]
    norm = math.sqrt(sum(x * x for x in raw))
    return [x / norm for x in raw]
