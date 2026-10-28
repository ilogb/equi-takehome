"""Analyze: OpenAPI -> tools, the in-process tool call as the asking user, and the answer loop.

No DB, no network: a fake session answers the compiled SQL (filtered by the user_id the
query itself carries) and a scripted FakeLLM plays the model.
"""

import asyncio
import json
import re
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.analyze.loop import MAX_TOOL_CALLS, SYSTEM_PROMPT, AnalyzeAnswer, answer_question
from app.analyze.tools import AnalyzeToolError, build_tools, call_tool
from app.api.search import get_llm
from app.auth.deps import current_user
from app.config import Settings
from app.db import get_session
from app.llm.base import ChatTurn, IncompleteResponse, LLMError, ToolCall
from app.llm.fake import FakeLLM
from app.main import create_app
from app.models import CommonRow, User

USER_A = User(id=1, email="a@example.com")
USER_B = User(id=2, email="b@example.com")


def settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://x/x",
        google_client_id="cid.apps.googleusercontent.com",
        google_client_secret="csecret",
        session_secret="s" * 48,
        fernet_key=Fernet.generate_key().decode(),
    )


def sql(stmt) -> str:
    text = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    return text.replace("%%", "%")


def common_row(id, user_id, document_id, entity, value) -> CommonRow:
    return CommonRow(
        id=id, user_id=user_id, document_id=document_id, entity=entity, entity_kind="fund", measure="return",
        period_kind="month", period_end=date(2026, 1, 31), value=Decimal(value), needs_review=False, conflict=False,
    )  # fmt: skip


class FakeSession:
    """Answers only what the SQL asks for: rows and documents owned by the user_id in the WHERE clause."""

    def __init__(self, rows=(), docs=None):
        self.rows = list(rows)  # (CommonRow, manager, document_name)
        self.docs = docs or {}  # document id -> (user_id, file name)
        self.users = {u.id: u for u in (USER_A, USER_B)}
        self.statements: list[str] = []

    def get(self, model, ident):
        return self.users.get(ident)

    def _uid(self, text: str, table: str) -> int:
        return int(re.search(rf"{table}\.user_id = (\d+)", text).group(1))

    def execute(self, stmt):
        text = sql(stmt)
        self.statements.append(text)
        if "FROM common_row" in text:
            uid = self._uid(text, "common_row")
            out = [SimpleNamespace(CommonRow=r, manager=m, document_name=n) for r, m, n in self.rows if r.user_id == uid]
        elif "FROM document" in text:
            uid = self._uid(text, "document")
            wanted = {int(x) for x in re.findall(r"\d+", re.search(r"document\.id IN \(([^)]*)\)", text).group(1))}
            out = [SimpleNamespace(id=i, file_name=n) for i, (u, n) in self.docs.items() if u == uid and i in wanted]
        else:
            out = []
        return SimpleNamespace(all=lambda: out, one=lambda: (None, None))

    def scalar(self, stmt):
        text = sql(stmt)
        self.statements.append(text)
        uid = self._uid(text, "common_row")
        return sum(1 for r, _, _ in self.rows if r.user_id == uid)

    def scalars(self, stmt):
        return SimpleNamespace(all=lambda: [])


def january_rows():
    return [
        (common_row(10, 1, 100, "Man AHL Diversified", "0.0842"), "Man Group", "man-ahl-jan-2026.pdf"),
        (common_row(11, 1, 101, "Fundsmith Equity", "0.0123"), "Fundsmith", "fundsmith-jan-2026.pdf"),
    ]


def make_app(db: FakeSession, llm=None):
    app = create_app(settings())
    app.dependency_overrides[get_session] = lambda: db
    if llm is not None:
        app.dependency_overrides[get_llm] = lambda: llm
    return app


def ask(app, db, user, question, script):
    llm = FakeLLM("/nonexistent", chat_script=script)
    answer = asyncio.run(answer_question(app, db, user, question, llm))
    return answer, llm


def final(payload: dict) -> ChatTurn:
    return ChatTurn(text=json.dumps(payload))


def rows_call(call_id="c1", **args) -> ChatTurn:
    args = args or {"measure": "return", "period_kind": "month", "start": "2026-01-01", "end": "2026-01-31",
                    "sort": "value", "order": "desc"}  # fmt: skip
    return ChatTurn(text=None, tool_calls=[ToolCall(call_id, "query_rows", args)])


# --- tools ---------------------------------------------------------------------------


def test_tools_only_analyze_get_routes():
    tools = build_tools(create_app(settings()))
    names = {t["name"] for t in tools}
    assert names == {"get_document", "query_rows", "list_funds", "describe_data", "search_documents"}
    for t in tools:
        assert t["type"] == "function" and t["strict"] is False
        assert t["description"]
        assert set(t) == {"type", "name", "description", "parameters", "strict"}  # no private keys leak
    by_name = {t["name"]: t for t in tools}
    rows = by_name["query_rows"]["parameters"]
    assert {"measure", "period_kind", "start", "end", "sort", "order", "limit"} <= set(rows["properties"])
    assert by_name["get_document"]["parameters"]["required"] == ["document_id"]
    assert "document" in rows["properties"]["document_id"]["description"]
    assert "rows_total" in by_name["get_document"]["description"]
    # nothing about identity is a model-visible parameter
    for t in tools:
        assert not any("internal" in p.lower() for p in t["parameters"]["properties"])


def test_analyze_route_without_operation_id_fails_startup():
    app = create_app(settings())
    router = APIRouter()

    @router.get("/api/extra", tags=["analyze"])
    def extra() -> dict:
        """Docstring present, operation id missing."""
        return {}

    app.include_router(router)
    app.openapi_schema = None
    with pytest.raises(RuntimeError, match="operation_id"):
        build_tools(app)


def test_post_routes_are_not_tools_even_if_tagged():
    app = create_app(settings())
    router = APIRouter()

    @router.post("/api/sneaky", tags=["analyze"], operation_id="sneaky")
    def sneaky() -> dict:
        """A write."""
        return {}

    app.include_router(router)
    app.openapi_schema = None
    assert "sneaky" not in {t["name"] for t in build_tools(app)}


def test_unknown_tool_is_a_tool_error_not_an_exception():
    app = make_app(FakeSession())
    out = asyncio.run(call_tool(app, USER_A.id, "delete_everything", {}))
    assert "error" in out
    out = asyncio.run(call_tool(app, USER_A.id, "export_rows_csv", {}))  # real route, not a tool
    assert "error" in out


def test_tool_missing_path_param_is_a_tool_error():
    out = asyncio.run(call_tool(make_app(FakeSession()), USER_A.id, "get_document", {}))
    assert "error" in out


# --- identity ------------------------------------------------------------------------


def test_analyze_tools_run_as_asking_user():
    """User B's tool call carries B's identity; the route scopes by it, so A's rows never come back."""
    db = FakeSession(rows=january_rows())
    app = make_app(db)  # current_user is NOT overridden: the real internal-identity path runs
    out = asyncio.run(call_tool(app, USER_B.id, "query_rows", {"measure": "return"}))
    assert out == {"rows": [], "total": 0}
    assert any("common_row.user_id = 2" in s for s in db.statements)
    assert not any("common_row.user_id = 1" in s for s in db.statements)

    out_a = asyncio.run(call_tool(app, USER_A.id, "query_rows", {"measure": "return"}))
    assert out_a["total"] == 2 and out_a["rows"][0]["entity"] == "Man AHL Diversified"


def test_question_from_b_never_returns_a_rows():
    db = FakeSession(rows=january_rows(), docs={100: (1, "man-ahl-jan-2026.pdf")})
    answer, llm = ask(make_app(db), db, USER_B, "best January?", [
        rows_call(),
        final({"text": "No January returns in your data.", "table": None, "sources": [100]}),
    ])  # fmt: skip
    tool_output = json.loads(llm.chat_calls[1]["messages"][-1]["output"])
    assert tool_output == {"rows": [], "total": 0}
    assert answer.sources == []  # A's document id is not B's to cite


def test_external_request_cannot_forge_internal_identity():
    app = make_app(FakeSession(rows=january_rows()))
    c = TestClient(app)
    assert c.get("/api/rows", headers={"X-Internal-User": "1"}).status_code == 401
    assert c.get("/api/rows", headers={"X-Internal-User": "1", "X-Internal-Token": "guess"}).status_code == 401
    assert c.get("/api/rows", headers={"X-Internal-Token": app.state.internal_token}).status_code == 401
    # the real secret works (this is what the in-process client sends)
    ok = c.get("/api/rows", headers={"X-Internal-User": "1", "X-Internal-Token": app.state.internal_token})
    assert ok.status_code == 200 and ok.json()["total"] == 2


def test_internal_secret_is_per_app_and_never_returned():
    a, b = create_app(settings()), create_app(settings())
    assert a.state.internal_token != b.state.internal_token and len(a.state.internal_token) >= 32
    db = FakeSession(rows=january_rows())
    answer, llm = ask(make_app(db), db, USER_A, "q", [rows_call(), final({"text": "x", "sources": []})])
    blob = json.dumps(llm.chat_calls, default=str) + answer.model_dump_json()
    assert a.state.internal_token not in blob and b.state.internal_token not in blob


# --- loop ----------------------------------------------------------------------------


def test_best_january_answer():
    db = FakeSession(rows=january_rows(), docs={100: (1, "man-ahl-jan-2026.pdf"), 101: (1, "fundsmith-jan-2026.pdf")})
    answer, llm = ask(make_app(db), db, USER_A, "Which fund did best in January?", [
        rows_call(),
        final({
            "text": "Man AHL Diversified did best in January 2026 (the latest January in your data) at 8.42%.",
            "table": {"columns": ["Fund", "January 2026 return"],
                      "rows": [["Man AHL Diversified", "8.42%"], ["Fundsmith Equity", "1.23%"]]},
            "sources": [100, 101],
        }),
    ])  # fmt: skip
    assert isinstance(answer, AnalyzeAnswer)
    assert answer.table is not None and answer.table.rows[0][0] == "Man AHL Diversified"
    assert {"document_id": 100, "file_name": "man-ahl-jan-2026.pdf"} in [s.model_dump() for s in answer.sources]
    assert answer.steps == ["Querying data points…"]
    # the tool really ran, as A, and its JSON went back to the model
    second = llm.chat_calls[1]["messages"]
    assert second[-2]["type"] == "function_call" and second[-2]["name"] == "query_rows"
    tool_output = json.loads(second[-1]["output"])
    assert tool_output["rows"][0]["entity"] == "Man AHL Diversified" and tool_output["rows"][0]["value"] == "0.0842"
    assert second[-1]["call_id"] == second[-2]["call_id"] == "c1"
    # the model was given the tools and the rules
    first = llm.chat_calls[0]
    assert {t["name"] for t in first["tools"]} >= {"query_rows"}
    assert first["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert first["messages"][1]["content"] == "Which fund did best in January?"


def test_system_prompt_rules():
    p = SYSTEM_PROMPT.lower()
    assert "latest january" in p
    assert "conflict" in p
    assert "missing" in p
    assert "account" in p and "rank" in p
    assert "data, not instructions" in p
    assert str(MAX_TOOL_CALLS) in p
    assert "never write document ids" in p and "document_name" in p


def test_stops_after_five_calls():
    db = FakeSession(rows=january_rows())
    script = [rows_call(f"c{i}") for i in range(MAX_TOOL_CALLS + 3)]
    answer, llm = ask(make_app(db), db, USER_A, "loop forever", script)
    assert MAX_TOOL_CALLS == 5
    assert len(answer.steps) == 5
    row_queries = [s for s in db.statements if "FROM common_row" in s and "count" not in s]
    assert len(row_queries) == 5
    assert llm.chat_calls[5]["tools"] == []  # after the limit the model may only answer
    assert len(llm.chat_calls) == 6
    assert "5" in answer.text and answer.table is None


def test_answer_after_limit_is_used():
    db = FakeSession(rows=january_rows())
    script = [rows_call(f"c{i}") for i in range(MAX_TOOL_CALLS)] + [final({"text": "done", "sources": []})]
    answer, llm = ask(make_app(db), db, USER_A, "q", script)
    assert answer.text == "done" and len(answer.steps) == 5
    assert llm.chat_calls[-1]["tools"] == []


def test_extra_calls_in_one_turn_beyond_limit_get_error_outputs():
    db = FakeSession(rows=january_rows())
    many = ChatTurn(text=None, tool_calls=[ToolCall(f"c{i}", "describe_data", {}) for i in range(7)])
    answer, llm = ask(make_app(db), db, USER_A, "q", [many, final({"text": "ok", "sources": []})])
    msgs = llm.chat_calls[1]["messages"]
    outputs = [m for m in msgs if m.get("type") == "function_call_output"]
    assert len(outputs) == 7  # every call gets an output, as the Responses API requires
    assert sum("limit" in o["output"] for o in outputs) == 2
    assert len(answer.steps) == 5


def test_unknown_source_ids_dropped():
    db = FakeSession(docs={100: (1, "man.pdf"), 200: (2, "someone-else.pdf")})
    answer, _ = ask(make_app(db), db, USER_A, "q", [
        final({"text": "t", "table": None, "sources": [100, 200, 999, "junk", 100]}),
    ])  # fmt: skip
    assert [s.model_dump() for s in answer.sources] == [{"document_id": 100, "file_name": "man.pdf"}]


def test_document_ids_in_the_text_become_file_names():
    db = FakeSession(docs={100: (1, "ishares_factsheet.pdf"), 200: (2, "someone-else.pdf")})
    answer, _ = ask(make_app(db), db, USER_A, "q", [
        final({
            "text": "iShares led at 15.25% (document 100). See also document_id 100, Doc #100 and document 200 (document 999).",
            "table": None,
            "sources": [100],
        }),
    ])  # fmt: skip
    # Known ids read as file names; another user's or unknown ids never leak a name.
    assert answer.text == (
        "iShares led at 15.25% (ishares_factsheet.pdf). See also ishares_factsheet.pdf, "
        "ishares_factsheet.pdf and a document."
    )


def test_plain_text_answer_is_kept():
    db = FakeSession()
    answer, _ = ask(make_app(db), db, USER_A, "q", [ChatTurn(text="Your data has no AUM figures.")])
    assert answer.text == "Your data has no AUM figures." and answer.table is None and answer.sources == []
    assert answer.retryable is False  # an answer, even an empty one, is not a failure to retry


def test_fenced_json_answer_parsed():
    db = FakeSession(docs={100: (1, "man.pdf")})
    fenced = "```json\n" + json.dumps({"text": "hi", "sources": [100]}) + "\n```"
    answer, _ = ask(make_app(db), db, USER_A, "q", [ChatTurn(text=fenced)])
    assert answer.text == "hi" and answer.sources[0].document_id == 100


def test_tool_error_is_returned_to_model():
    db = FakeSession()
    script = [
        ChatTurn(text=None, tool_calls=[ToolCall("c1", "drop_tables", {})]),
        final({"text": "sorry", "sources": []}),
    ]
    answer, llm = ask(make_app(db), db, USER_A, "q", script)
    out = json.loads(llm.chat_calls[1]["messages"][-1]["output"])
    assert "error" in out and answer.text == "sorry"


def test_step_labels():
    from app.analyze.loop import step_label

    assert step_label("query_rows", {}) == "Querying data points…"
    assert step_label("get_document", {"document_id": 7}) == "Reading document 7…"
    assert step_label("search_documents", {"q": "Terry Smith"}) == "Searching documents for “Terry Smith”…"
    assert step_label("search_documents", {}) == "Searching documents…"
    assert step_label("made_up", {}) == "Calling made_up…"


def test_tool_error_class_exported():
    assert issubclass(AnalyzeToolError, Exception)


# --- route ---------------------------------------------------------------------------


def test_analyze_route_returns_answer():
    db = FakeSession(rows=january_rows(), docs={100: (1, "man-ahl-jan-2026.pdf")})
    llm = FakeLLM("/nonexistent", chat_script=[rows_call(), final({"text": "Man AHL", "sources": [100]})])
    app = make_app(db, llm)
    app.dependency_overrides[current_user] = lambda: USER_A
    resp = TestClient(app).post("/api/analyze", json={"question": "Which fund did best in January?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "Man AHL" and body["steps"] == ["Querying data points…"]
    assert body["sources"] == [{"document_id": 100, "file_name": "man-ahl-jan-2026.pdf"}]
    assert body["table"] is None


def test_analyze_route_requires_sign_in_and_question():
    app = make_app(FakeSession())
    c = TestClient(app)
    assert c.post("/api/analyze", json={"question": "x"}).status_code == 401
    app.dependency_overrides[current_user] = lambda: USER_A
    assert c.post("/api/analyze", json={"question": ""}).status_code == 422


def test_analyze_route_is_not_itself_a_tool():
    spec = create_app(settings()).openapi()
    op = spec["paths"]["/api/analyze"]["post"]
    assert op["tags"] == ["analyze"] and op["operationId"] == "analyze"
    assert "analyze" not in {t["name"] for t in build_tools(create_app(settings()))}


# --- review fixes: bounded work, graceful failure, path and id validation -------------


def test_each_chat_call_bounded_by_remaining_budget():
    from app.analyze.loop import BUDGET_S

    db = FakeSession(rows=january_rows())
    _, llm = ask(make_app(db), db, USER_A, "q", [rows_call(), final({"text": "x", "sources": []})])
    timeouts = [c["timeout"] for c in llm.chat_calls]
    assert all(t is not None and 0 < t <= BUDGET_S for t in timeouts)
    assert timeouts[1] <= timeouts[0]


@pytest.mark.parametrize("error", [LLMError("down", retryable=True), IncompleteResponse()])
def test_llm_failure_is_graceful_answer(error):
    from app.analyze.loop import UNAVAILABLE

    db = FakeSession(rows=january_rows(), docs={100: (1, "man.pdf")})
    answer, _ = ask(make_app(db), db, USER_A, "q", [rows_call(), error])
    assert answer.text == UNAVAILABLE == "Couldn't answer right now — try again."
    assert answer.table is None and answer.sources == [] and answer.steps == ["Querying data points…"]
    assert answer.retryable is True


def test_llm_failure_through_route_is_not_500():
    llm = FakeLLM("/nonexistent", chat_script=[LLMError("down", retryable=False)])
    app = make_app(FakeSession(), llm)
    app.dependency_overrides[current_user] = lambda: USER_A
    resp = TestClient(app).post("/api/analyze", json={"question": "q"})
    assert resp.status_code == 200 and resp.json()["text"] == "Couldn't answer right now — try again."
    assert resp.json()["retryable"] is True


def test_malformed_arguments_become_tool_error():
    db = FakeSession(rows=january_rows())
    bad = ChatTurn(text=None, tool_calls=[ToolCall("c1", "query_rows", {}, error="arguments were not valid JSON")])
    answer, llm = ask(make_app(db), db, USER_A, "q", [bad, final({"text": "ok", "sources": []})])
    out = json.loads(llm.chat_calls[1]["messages"][-1]["output"])
    assert "not valid JSON" in out["error"]
    assert not any("FROM common_row" in s for s in db.statements)  # nothing ran
    assert answer.text == "ok" and answer.steps == []


@pytest.mark.parametrize("bad", ["1/x", "..", "../rows", "1?x=2", True, 1.5, -1, ["1"]])
def test_path_param_validated_before_substitution(bad):
    db = FakeSession(rows=january_rows())
    out = asyncio.run(call_tool(make_app(db), USER_A.id, "get_document", {"document_id": bad}))
    assert "error" in out and "integer" in out["error"]
    assert db.statements == []  # no request reached a route


def test_string_path_param_must_be_safe_segment():
    from app.analyze.tools import _path_value

    p = {"name": "slug", "schema": {"type": "string"}}
    assert _path_value("t", p, "abc_D-1") == "abc_D-1"
    for bad in ["..", "a/b", "a b", "%2e", ""]:
        with pytest.raises(AnalyzeToolError):
            _path_value("t", p, bad)


def test_raising_tool_route_is_tool_error_not_500():
    app = create_app(settings())
    router = APIRouter()

    @router.get("/api/boom", tags=["analyze"], operation_id="boom")
    def boom() -> dict:
        """Always fails."""
        raise RuntimeError("secret internals")

    app.include_router(router)
    app.openapi_schema = None
    app.dependency_overrides[get_session] = lambda: FakeSession()
    out = asyncio.run(call_tool(app, USER_A.id, "boom", {}))
    assert out == {"error": "boom failed"}

    llm = FakeLLM("/nonexistent", chat_script=[
        ChatTurn(text=None, tool_calls=[ToolCall("c1", "boom", {})]), final({"text": "sorry", "sources": []}),
    ])  # fmt: skip
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[current_user] = lambda: USER_A
    resp = TestClient(app).post("/api/analyze", json={"question": "q"})
    assert resp.status_code == 200 and resp.json()["text"] == "sorry"
    assert json.loads(llm.chat_calls[1]["messages"][-1]["output"]) == {"error": "boom failed"}


def test_out_of_range_source_ids_dropped_before_query():
    db = FakeSession(docs={100: (1, "man.pdf")})
    answer, _ = ask(make_app(db), db, USER_A, "q", [
        final({"text": "t", "sources": ["99999999999999999999", 2**63, 0, -5, 100]}),
    ])  # fmt: skip
    assert [s.document_id for s in answer.sources] == [100]
    doc_queries = [s for s in db.statements if "FROM document" in s]
    assert doc_queries and "99999999999999999999" not in doc_queries[0] and str(2**63) not in doc_queries[0]
