"""LLMProvider backed by the OpenAI Responses API."""

import base64
import json
from pathlib import Path

import openai
from openai import OpenAI
from openai.lib._pydantic import to_strict_json_schema
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.llm.base import ChatTurn, IncompleteResponse, LLMError, ToolCall
from app.pipeline.schema import CsvMapping, DocumentExtraction

MAX_OUTPUT_TOKENS = 100_000
TIMEOUT_SECONDS = 600
_PROMPTS = Path(__file__).resolve().parents[1] / "pipeline" / "prompts"
_RETRYABLE = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.RateLimitError,
    openai.InternalServerError,
)


def _prompt(name: str) -> str:
    return (_PROMPTS / name).read_text()


class OpenAIProvider:
    def __init__(self, settings: Settings, client: OpenAI | None = None):
        self.settings = settings
        self.client = client or OpenAI(api_key=settings.openai_api_key, timeout=TIMEOUT_SECONDS)

    def extract(
        self, *, file_name: str, pdf: bytes | None, text: str | None, known_funds: list[str]
    ) -> DocumentExtraction:
        if (pdf is None) == (text is None):
            raise ValueError("extract needs exactly one of pdf or text")
        known = "\n".join(f"- {n}" for n in known_funds) or "(none)"
        parts: list[dict] = []
        if pdf is not None:
            parts.append({
                "type": "input_file",
                "filename": file_name,
                "file_data": "data:application/pdf;base64," + base64.b64encode(pdf).decode(),
            })
            parts.append({"type": "input_text", "text": f"KNOWN FUNDS:\n{known}\nExtract per the schema."})
        else:
            parts.append({
                "type": "input_text",
                "text": f"KNOWN FUNDS:\n{known}\n<document>\n{text}\n</document>\nExtract per the schema.",
            })
        return self._structured(
            model=self.settings.extraction_model,
            system=_prompt("extract_v1.md"),
            content=parts,
            schema_model=DocumentExtraction,
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )

    def map_table(self, *, name: str, head: list[list[str]], tail: list[list[str]]) -> CsvMapping:
        lines = [f"{i}: {_join(r)}" for i, r in enumerate(head)]
        if tail:
            start = len(head)
            lines.append("...")
            lines += [f"{start + i}: {_join(r)}" for i, r in enumerate(tail)]
        body = f"Table name: {name}\n<table>\n" + "\n".join(lines) + "\n</table>"
        return self._structured(
            model=self.settings.mapping_model,
            system=_prompt("mapping_v1.md"),
            content=[{"type": "input_text", "text": body}],
            schema_model=CsvMapping,
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._call(
            self.client.embeddings.create, model=self.settings.embedding_model, input=texts
        )
        return [d.embedding for d in resp.data]

    def chat(self, *, messages: list[dict], tools: list[dict]) -> ChatTurn:
        resp = self._call(
            self.client.responses.create,
            model=self.settings.analyze_model,
            input=messages,
            tools=tools,
        )
        self._check_complete(resp)
        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for item in resp.output:
            if item.type == "function_call":
                calls.append(ToolCall(item.call_id, item.name, json.loads(item.arguments or "{}")))
            elif item.type == "message":
                text_parts += [c.text for c in item.content if c.type == "output_text"]
        return ChatTurn(text="".join(text_parts) or None, tool_calls=calls)

    # -- internals ---------------------------------------------------------

    def _structured(self, *, model, system, content, schema_model: type[BaseModel], **extra):
        """One strict-json_schema call, with a single repair retry on invalid output."""
        input_: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ]
        text_format = {
            "format": {
                "type": "json_schema",
                "name": schema_model.__name__.lower(),
                "strict": True,
                "schema": to_strict_json_schema(schema_model),
            }
        }
        for attempt in range(2):
            resp = self._call(
                self.client.responses.create, model=model, input=input_, text=text_format, **extra
            )
            self._check_complete(resp)
            try:
                return schema_model.model_validate_json(resp.output_text)
            except ValidationError as err:
                if attempt == 1:
                    raise LLMError(f"model output failed schema validation: {err}", retryable=True) from err
                input_ = input_ + [
                    {"role": "assistant", "content": resp.output_text},
                    {
                        "role": "user",
                        "content": "Your previous output failed schema validation. "
                        f"Fix these errors and return the complete corrected JSON:\n{err}",
                    },
                ]
        raise AssertionError("unreachable")

    @staticmethod
    def _check_complete(resp) -> None:
        if getattr(resp, "status", None) == "incomplete":
            reason = getattr(getattr(resp, "incomplete_details", None), "reason", None)
            raise IncompleteResponse(f"response incomplete: {reason}")

    @staticmethod
    def _call(fn, **kwargs):
        try:
            return fn(**kwargs)
        except _RETRYABLE as err:
            raise LLMError(str(err), retryable=True) from err
        except openai.OpenAIError as err:
            raise LLMError(str(err), retryable=False) from err


def _join(row: list[str]) -> str:
    return ",".join(row)
