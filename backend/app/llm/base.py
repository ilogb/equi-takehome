"""LLM provider interface shared by the real OpenAI client and the test fake."""

from dataclasses import dataclass, field
from typing import Protocol

from app.pipeline.schema import CsvMapping, DocumentExtraction

PROMPT_VERSION = "extract-v1"


class LLMError(Exception):
    def __init__(self, message: str, *, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


class IncompleteResponse(LLMError):
    """The model hit its output limit; a retry may succeed, so it is always retryable."""

    def __init__(self, message: str = "response incomplete"):
        super().__init__(message, retryable=True)


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass(frozen=True)
class ChatTurn:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(Protocol):
    def extract(
        self, *, file_name: str, pdf: bytes | None, text: str | None, known_funds: list[str]
    ) -> DocumentExtraction: ...

    def map_table(
        self, *, name: str, head: list[list[str]], tail: list[list[str]]
    ) -> CsvMapping: ...

    def embed(self, texts: list[str]) -> list[list[float]]: ...

    def chat(self, *, messages: list[dict], tools: list[dict]) -> ChatTurn: ...
