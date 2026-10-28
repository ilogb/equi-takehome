"""Library dashboard: document and figure counts, latest 1-year return vs benchmark, latest AUM.

Not tagged `analyze`: it summarises for the page and is not a tool for the model.
"""

from collections.abc import Iterable, Sequence
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import Select, func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from app.api.serialize import dec_str
from app.auth.deps import current_user
from app.db import get_session
from app.models import CommonRow, SourceFile, User

router = APIRouter(prefix="/api")

_PENDING = {"queued", "processing"}


def status_counts_query(user_id: int) -> Select:
    return (
        select(SourceFile.status, func.count())
        .where(SourceFile.user_id == user_id)
        .group_by(SourceFile.status)
    )


def row_totals_query(user_id: int) -> Select:
    return select(
        func.count().label("rows"),
        func.count(func.distinct(CommonRow.entity))
        .filter(CommonRow.entity_kind == "fund")
        .label("funds"),
        func.count(func.distinct(CommonRow.entity))
        .filter(CommonRow.entity_kind == "account")
        .label("accounts"),
        func.count().filter(CommonRow.needs_review).label("needs_review"),
        func.count().filter(CommonRow.conflict).label("conflicts"),
    ).where(CommonRow.user_id == user_id)


def latest_query(user_id: int, measures: Sequence[str], period_kind: str | None = None) -> Select:
    """The newest row per fund and measure (accounts excluded)."""
    q = (
        select(
            CommonRow.entity,
            CommonRow.fund_id,
            CommonRow.measure,
            CommonRow.value,
            CommonRow.period_end,
            CommonRow.currency,
        )
        .ext(distinct_on(CommonRow.entity, CommonRow.measure))
        .where(
            CommonRow.user_id == user_id,
            CommonRow.entity_kind == "fund",
            CommonRow.measure.in_(measures),
        )
        .order_by(CommonRow.entity, CommonRow.measure, CommonRow.period_end.desc(), CommonRow.id)
    )
    if period_kind is not None:
        q = q.where(CommonRow.period_kind == period_kind)
    return q


def assemble(
    statuses: Iterable[tuple[str, int]], totals: Any, one_year: Iterable[Any], aum: Iterable[Any]
) -> dict:
    counts = dict(statuses)
    documents = {
        # Unsupported files (images, notes) are not documents; they are left out of the total.
        "total": sum(n for s, n in counts.items() if s != "unsupported"),
        "done": counts.get("done", 0),
        "needs_review": counts.get("needs_review", 0),
        "failed": counts.get("failed", 0) + counts.get("scanned_no_text", 0),
        "processing": sum(counts.get(s, 0) for s in _PENDING),
    }

    paired: dict[str, dict] = {}
    for r in one_year:
        entry = paired.setdefault(
            r.entity,
            {
                "entity": r.entity,
                "fund_id": r.fund_id,
                "period_end": None,
                "return": None,
                "benchmark": None,
            },
        )
        if r.measure == "return":
            entry["return"] = dec_str(r.value)
            entry["period_end"] = r.period_end.isoformat()
        else:
            entry["benchmark"] = dec_str(r.value)
    one_year_out = sorted(
        (
            e for e in paired.values() if e["return"] is not None
        ),  # a benchmark alone has nothing to compare
        key=lambda e: float(e["return"]),
        reverse=True,
    )

    aum_out = [
        {
            "entity": r.entity,
            "fund_id": r.fund_id,
            "period_end": r.period_end.isoformat(),
            "value": dec_str(r.value),
            "currency": r.currency,
        }
        for r in sorted(aum, key=lambda r: r.value, reverse=True)
    ]

    return {
        "documents": documents,
        "figures": {
            "total": totals.rows,
            "needs_review": totals.needs_review,
            "conflicts": totals.conflicts,
        },
        "entities": {"funds": totals.funds, "accounts": totals.accounts},
        "one_year": one_year_out,
        "aum": aum_out,
    }


def load(session: Session, user_id: int) -> dict:
    return assemble(
        statuses=session.execute(status_counts_query(user_id)).all(),
        totals=session.execute(row_totals_query(user_id)).one(),
        one_year=session.execute(
            latest_query(user_id, ["return", "benchmark_return"], period_kind="1y")
        ).all(),
        aum=session.execute(latest_query(user_id, ["aum"])).all(),
    )


@router.get("/dashboard")
def dashboard(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    return load(session, user.id)
