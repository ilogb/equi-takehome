from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.api import files as files_api
from app.api.files import files_query
from app.api.funds import funds_query
from app.api.rows import MAX_LIMIT, RowFilters, rows_count_query, rows_csv, rows_query
from app.auth.deps import current_user, user_source
from app.config import Settings
from app.db import get_session
from app.main import create_app
from app.models import SourceFile, User
from app.sources.base import SourceError


def sql(stmt) -> str:
    text = str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    return text.replace("%%", "%")  # pyformat escaping of literal percent signs


def settings() -> Settings:
    return Settings(session_secret="s" * 32, public_base_url="http://localhost:8000")


# --- query builders -------------------------------------------------------------------


def test_rows_query_always_scoped_to_user():
    assert "common_row.user_id = 7" in sql(rows_query(7, RowFilters()))
    assert "common_row.user_id = 7" in sql(rows_count_query(7, RowFilters()))
    full = RowFilters(fund="x", manager="m", measure="return", start=date(2026, 1, 1), conflict=True)
    assert "common_row.user_id = 7" in sql(rows_query(7, full))


def test_rows_query_filters_map_to_columns():
    f = RowFilters(
        fund="Alpha", manager="Man", entity_kind="fund", share_class="I", measure="return",
        period_kind="month", start=date(2026, 1, 1), end=date(2026, 1, 31), needs_review=True, conflict=False,
    )  # fmt: skip
    text = sql(rows_query(1, f))
    for part in [
        "common_row.entity ILIKE '%Alpha%'",
        "document.manager ILIKE '%Man%'",
        "common_row.entity_kind = 'fund'",
        "common_row.share_class = 'I'",
        "common_row.measure = 'return'",
        "common_row.period_kind = 'month'",
        "common_row.period_end >= '2026-01-01'",
        "common_row.period_end <= '2026-01-31'",
        "common_row.needs_review = true",
        "common_row.conflict = false",
    ]:
        assert part in text, part
    assert "common_row.fund_id = 12" in sql(rows_query(1, RowFilters(fund="12")))


def test_rows_query_sort_order_and_limit():
    text = sql(rows_query(1, RowFilters(sort="value", order="desc", limit=50, offset=10)))
    assert "ORDER BY common_row.value DESC, common_row.id" in text
    assert "LIMIT 50 OFFSET 10" in text
    assert "ORDER BY common_row.entity ASC" in sql(rows_query(1, RowFilters(sort="entity", order="asc")))
    assert "ORDER BY common_row.period_end DESC" in sql(rows_query(1, RowFilters()))
    assert f"LIMIT {MAX_LIMIT}" in sql(rows_query(1, RowFilters(limit=99999)))


def test_files_and_funds_queries_scoped_to_user():
    assert "source_file.user_id = 9" in sql(files_query(9))
    assert "source_file.user_id = 9" in sql(files_query(9, status="done", q="abc"))
    assert "source_file.status = 'done'" in sql(files_query(9, status="done"))
    assert "fund.user_id = 9" in sql(funds_query(9))
    assert "common_row.user_id = 9" in sql(funds_query(9))


# --- CSV ----------------------------------------------------------------------------


def row(**kw):
    base = dict(
        document_name="a.pdf", entity="Man AHL", entity_kind="fund", share_class=None, measure="return",
        period_kind="month", period_end=date(2026, 1, 31), value="0.0842", value_as_written="8.42%",
        unit="fraction", currency=None, benchmark_name=None, needs_review=False, conflict=False,
    )  # fmt: skip
    base.update(kw)
    return base


def test_csv_header_and_decimal_strings():
    lines = rows_csv([row(), row(measure="aum", value="1500000.5000000000")]).splitlines()
    assert lines[0].startswith("document_name,entity,entity_kind,share_class,measure")
    first = lines[1].split(",")
    assert first[7] == "0.0842"  # raw value, not float-formatted
    assert first[8] == "8.42%"  # display column
    assert lines[2].split(",")[7] == "1500000.5000000000"
    assert lines[2].split(",")[8] == ""  # no percent for AUM


def test_csv_percent_is_exact_decimal():
    assert Decimal("0.0001") * 100 == Decimal("0.0100")
    assert rows_csv([row(value="0.1234")]).splitlines()[1].split(",")[8] == "12.34%"


# --- routes -------------------------------------------------------------------------


class FakeSession:
    def __init__(self, file=None):
        self.file = file
        self.commits = 0

    def scalar(self, stmt):
        return self.file

    def commit(self):
        self.commits += 1


class FakeSource:
    def __init__(self, chunks=(), error=None):
        self.chunks, self.error = chunks, error

    def stream(self, file_id):
        if self.error:
            raise self.error
        yield from self.chunks


def make_file(mime="application/pdf") -> SourceFile:
    return SourceFile(id=5, user_id=1, drive_file_id="d1", name="a", path="", mime_type=mime, status="done")


def client(file, source=None) -> tuple[TestClient, FakeSession]:
    app = create_app(settings())
    db = FakeSession(file)
    user = User(id=1, email="a@b.c")
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[user_source] = lambda: source
    return TestClient(app), db


def test_content_passes_content_type():
    c, _ = client(make_file(), FakeSource([b"%PDF", b"-1.7"]))
    resp = c.get("/api/files/5/content")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content == b"%PDF-1.7"
    assert "content-security-policy" not in resp.headers


def test_content_html_is_sandboxed():
    c, _ = client(make_file("text/html"), FakeSource([b"<p>x</p>"]))
    resp = c.get("/api/files/5/content")
    assert resp.headers["content-security-policy"] == "sandbox"
    assert resp.headers["content-type"].startswith("text/html")


def test_content_404_marks_missing():
    f = make_file()
    c, db = client(f, FakeSource(error=SourceError("gone", retryable=False, status=404)))
    resp = c.get("/api/files/5/content")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "No longer in Drive"}
    assert f.missing_in_drive is True
    assert db.commits == 1


def test_content_unknown_file_is_404():
    c, _ = client(None, FakeSource())
    assert c.get("/api/files/5/content").status_code == 404


def test_content_other_drive_error_is_502():
    c, _ = client(make_file(), FakeSource(error=SourceError("boom", status=500)))
    assert c.get("/api/files/5/content").status_code == 502


def test_retry_and_reextract_force_enqueue(monkeypatch):
    calls = []
    monkeypatch.setattr(files_api, "enqueue", lambda s, fid, force=False: calls.append((fid, force)))
    c, db = client(make_file())
    assert c.post("/api/files/5/retry").status_code == 200
    assert c.post("/api/files/5/reextract").status_code == 200
    assert calls == [(5, True), (5, True)]
    assert db.commits == 2


def test_retry_unknown_file_is_404(monkeypatch):
    monkeypatch.setattr(files_api, "enqueue", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    c, _ = client(None)
    assert c.post("/api/files/5/retry").status_code == 404


def test_file_json_shape():
    r = SimpleNamespace(
        id=1, name="a.pdf", path="x/a.pdf", mime_type="application/pdf", status="done", error=None,
        missing_in_drive=False, doc_type="factsheet", manager="M", funds=["F"], as_of_date=date(2026, 1, 31),
        tags=["t"], row_count=3, created_at=None,
    )  # fmt: skip
    out = files_api.file_json(r)
    assert out["kind"] == "pdf" and out["row_count"] == 3 and out["updated_at"] is None


def test_analyze_routes_have_operation_ids():
    spec = create_app(settings()).openapi()
    found = {}
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            if "analyze" in op.get("tags", []):
                assert op.get("operationId") and not op["operationId"].startswith(("get_document_api", "query_rows_api")), path
                assert op.get("description"), path
                found[op["operationId"]] = path
    assert found == {
        "get_document": "/api/documents/{document_id}",
        "query_rows": "/api/rows",
        "list_funds": "/api/funds",
        "describe_data": "/api/meta",
    }
