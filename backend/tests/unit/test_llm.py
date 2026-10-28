import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.llm.base import ChatTurn, IncompleteResponse, LLMError
from app.llm.fake import FakeLLM
from app.llm.openai_provider import OpenAIProvider
from app.models import EMBEDDING_DIMS
from app.pipeline.schema import CsvMapping, DocumentExtraction

RECORDED = Path(__file__).resolve().parents[1] / "recorded"
MAN = "man-ahl_factsheet_2026-08.pdf"


class StubResponses:
    def __init__(self, replies):
        self.replies = list(replies)
        self.requests: list[dict] = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.replies.pop(0)


def reply(output_text="", status="completed"):
    return SimpleNamespace(
        status=status, output_text=output_text, incomplete_details=None, output=[]
    )


def provider(*replies):
    stub = SimpleNamespace(responses=StubResponses(replies))
    return OpenAIProvider(Settings(openai_api_key="x"), client=stub), stub.responses


def valid_json():
    return (RECORDED / f"{MAN}.json").read_text()


def test_pdf_request_shape():
    p, responses = provider(reply(valid_json()))
    out = p.extract(file_name=MAN, pdf=b"%PDF-1.7 fake", text=None, known_funds=["Man AHL Diversified"])
    assert isinstance(out, DocumentExtraction)
    req = responses.requests[0]
    parts = req["input"][1]["content"]
    files = [x for x in parts if x["type"] == "input_file"]
    assert len(files) == 1
    assert files[0]["file_data"] == "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.7 fake").decode()
    assert req["text"]["format"]["type"] == "json_schema"
    assert req["text"]["format"]["strict"] is True
    assert req["max_output_tokens"] == 100000
    assert req["model"] == "gpt-6.1-sol"
    assert "Man AHL Diversified" in json.dumps(parts)


def test_text_request_wraps_document_tags():
    p, responses = provider(reply(valid_json()))
    p.extract(file_name="x.eml", pdf=None, text="hello", known_funds=[])
    part = responses.requests[0]["input"][1]["content"][0]
    assert "<document>\nhello\n</document>" in part["text"]


def test_incomplete_raises_retryable():
    p, _ = provider(reply(status="incomplete"))
    with pytest.raises(IncompleteResponse) as exc:
        p.extract(file_name=MAN, pdf=b"x", text=None, known_funds=[])
    assert exc.value.retryable is True
    assert isinstance(exc.value, LLMError)


def test_schema_repair_retry_once():
    p, responses = provider(reply('{"doc_type": "nonsense"}'), reply(valid_json()))
    out = p.extract(file_name=MAN, pdf=b"x", text=None, known_funds=[])
    assert out.rows
    assert len(responses.requests) == 2
    second = json.dumps(responses.requests[1]["input"])
    assert "doc_type" in second and "validation" in second


def test_schema_repair_gives_up_after_one_retry():
    p, responses = provider(reply("{}"), reply("{}"))
    with pytest.raises(LLMError):
        p.extract(file_name=MAN, pdf=b"x", text=None, known_funds=[])
    assert len(responses.requests) == 2


def test_map_table_request_and_result():
    mapping = (RECORDED / "map_northwind-capital_monthly-returns_2026-09.json").read_text()
    p, responses = provider(reply(mapping))
    out = p.map_table(name="n.csv", head=[["Fund", "Period"], ["A", "2026-01-31"]], tail=[["B", "x"]])
    assert isinstance(out, CsvMapping) and out.layout == "long"
    req = responses.requests[0]
    assert req["model"] == "gpt-6.1-terra"
    assert "0: Fund,Period" in req["input"][1]["content"][0]["text"]


def test_fake_replays_recorded():
    out = FakeLLM(RECORDED).extract(file_name=MAN, pdf=None, text=None, known_funds=[])
    assert sum(1 for r in out.rows if r.measure == "return") >= 9


def test_fake_replays_every_recorded_extraction():
    fake = FakeLLM(RECORDED)
    for path in [*RECORDED.glob("*.pdf.json"), *RECORDED.glob("*.eml.json")]:
        assert fake.extract(file_name=path.name.removesuffix(".json")).rows


def test_fake_missing_recording_is_not_retryable():
    with pytest.raises(LLMError) as exc:
        FakeLLM(RECORDED).extract(file_name="nope.pdf")
    assert exc.value.retryable is False


def test_fake_map_table():
    out = FakeLLM(RECORDED).map_table(name="alderbank_performance-summary_2026-09.csv", head=[], tail=[])
    assert out.layout == "wide" and out.skip_top == 3


def test_embed_dims():
    vec = FakeLLM(RECORDED).embed(["a"])[0]
    assert len(vec) == EMBEDDING_DIMS == 1536


def test_embed_deterministic_unit_vectors():
    a1, a2, b = FakeLLM(RECORDED).embed(["a", "a", "b"])
    assert a1 == a2 != b
    assert sum(x * x for x in a1) == pytest.approx(1.0)


def test_fake_chat_replays_script():
    turns = [ChatTurn(text="one"), ChatTurn(text="two")]
    fake = FakeLLM(RECORDED, chat_script=turns)
    assert fake.chat(messages=[], tools=[]).text == "one"
    assert fake.chat(messages=[], tools=[]).text == "two"
    with pytest.raises(LLMError):
        fake.chat(messages=[], tools=[])


@pytest.mark.parametrize("model", [DocumentExtraction, CsvMapping])
def test_schemas_are_strict_compatible(model):
    from openai.lib._pydantic import to_strict_json_schema

    def walk(node):
        if isinstance(node, dict):
            if "properties" in node:
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(to_strict_json_schema(model))
