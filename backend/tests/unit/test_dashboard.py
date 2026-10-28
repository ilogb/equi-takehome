from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy.dialects import postgresql

from app.api.dashboard import (
    assemble,
    latest_query,
    row_totals_query,
    status_counts_query,
)
from app.auth.deps import current_user
from app.config import Settings
from app.db import get_session
from app.main import create_app
from app.models import User


def sql(stmt) -> str:
    return str(stmt.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))


def latest(entity, measure, value, period_end=date(2026, 9, 30), currency="USD", fund_id=1):
    return SimpleNamespace(
        entity=entity,
        fund_id=fund_id,
        measure=measure,
        value=Decimal(value),
        period_end=period_end,
        currency=currency,
    )


def test_every_query_is_scoped_to_the_user():
    assert "source_file.user_id = 7" in sql(status_counts_query(7))
    assert "common_row.user_id = 7" in sql(row_totals_query(7))
    assert "common_row.user_id = 7" in sql(latest_query(7, ["aum"]))


def test_latest_query_takes_the_newest_fund_row_per_entity_and_measure():
    text = sql(latest_query(1, ["return", "benchmark_return"], period_kind="1y"))
    assert "DISTINCT ON (common_row.entity, common_row.measure)" in text
    assert "ORDER BY common_row.entity, common_row.measure, common_row.period_end DESC" in text
    assert "common_row.entity_kind = 'fund'" in text  # accounts are not funds
    assert "common_row.period_kind = '1y'" in text


def test_assemble_counts_documents_and_rows():
    out = assemble(
        statuses=[("done", 11), ("needs_review", 2), ("failed", 1), ("unsupported", 2)],
        totals=SimpleNamespace(rows=58763, funds=29, accounts=1, needs_review=30, conflicts=30),
        one_year=[],
        aum=[],
    )
    assert out["documents"] == {
        "total": 14,
        "done": 11,
        "needs_review": 2,
        "failed": 1,
        "processing": 0,
    }
    assert out["figures"] == {"total": 58763, "needs_review": 30, "conflicts": 30}
    assert out["entities"] == {"funds": 29, "accounts": 1}


def test_assemble_pairs_fund_and_benchmark_and_sorts_best_first():
    out = assemble(
        statuses=[],
        totals=SimpleNamespace(rows=0, funds=0, accounts=0, needs_review=0, conflicts=0),
        one_year=[
            latest("JPMorgan Equity Focus ETF", "return", "0.1032", fund_id=2),
            latest("JPMorgan Equity Focus ETF", "benchmark_return", "0.1574", fund_id=2),
            latest("Man AHL Diversified plc", "return", "0.3678", date(2026, 8, 31), fund_id=3),
        ],
        aum=[],
    )
    assert out["one_year"] == [
        {
            "entity": "Man AHL Diversified plc",
            "fund_id": 3,
            "period_end": "2026-08-31",
            "return": "0.3678",
            "benchmark": None,
        },
        {
            "entity": "JPMorgan Equity Focus ETF",
            "fund_id": 2,
            "period_end": "2026-09-30",
            "return": "0.1032",
            "benchmark": "0.1574",
        },
    ]


def test_assemble_lists_aum_largest_first_in_its_own_currency():
    out = assemble(
        statuses=[],
        totals=SimpleNamespace(rows=0, funds=0, accounts=0, needs_review=0, conflicts=0),
        one_year=[],
        aum=[
            latest("Man AHL Diversified plc", "aum", "313174253", currency="USD", fund_id=3),
            latest("Fundsmith SICAV Equity Fund", "aum", "4500000000", currency="EUR", fund_id=4),
        ],
    )
    assert [(a["entity"], a["value"], a["currency"]) for a in out["aum"]] == [
        ("Fundsmith SICAV Equity Fund", "4500000000", "EUR"),
        ("Man AHL Diversified plc", "313174253", "USD"),
    ]


def test_route_requires_sign_in_and_is_not_an_analyze_tool():
    app = create_app(Settings(session_secret="s" * 32, public_base_url="http://localhost:8000"))
    assert TestClient(app).get("/api/dashboard").status_code == 401
    assert "analyze" not in app.openapi()["paths"]["/api/dashboard"]["get"].get("tags", [])


def test_route_returns_the_assembled_summary(monkeypatch):
    import app.api.dashboard as dash

    monkeypatch.setattr(dash, "load", lambda session, user_id: {"documents": {"total": user_id}})
    app = create_app(Settings(session_secret="s" * 32, public_base_url="http://localhost:8000"))
    app.dependency_overrides[current_user] = lambda: User(id=5, email="a@example.com")
    app.dependency_overrides[get_session] = lambda: None
    assert TestClient(app).get("/api/dashboard").json() == {"documents": {"total": 5}}
