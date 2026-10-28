"""Query extracted rows (JSON and CSV)."""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.api.serialize import dec_str
from app.auth.deps import current_user
from app.db import get_session
from app.models import CommonRow, Document, SourceFile, User

router = APIRouter(prefix="/api")

MAX_LIMIT = 500
CSV_COLUMNS = [
    "document_name", "entity", "entity_kind", "share_class", "measure", "period_kind",
    "period_end", "value", "value_percent", "value_as_written", "unit", "currency",
    "benchmark_name", "needs_review", "conflict",
]  # fmt: skip
_SORTS = {"value": CommonRow.value, "period_end": CommonRow.period_end, "entity": CommonRow.entity}
_RETURN_MEASURES = {"return", "benchmark_return", "account_return"}


@dataclass
class RowFilters:
    fund: str | None = None
    manager: str | None = None
    entity_kind: str | None = None
    share_class: str | None = None
    measure: str | None = None
    period_kind: str | None = None
    start: date | None = None
    end: date | None = None
    needs_review: bool | None = None
    conflict: bool | None = None
    document_id: int | None = None
    sort: str = "period_end"
    order: str = "desc"
    limit: int = 100
    offset: int = 0


def _filtered(user_id: int, f: RowFilters) -> Select:
    """The user_id predicate is unconditional; every filter only narrows it."""
    stmt = (
        select(CommonRow, Document.manager.label("manager"), SourceFile.name.label("document_name"))
        .select_from(CommonRow)
        .join(Document, Document.id == CommonRow.document_id)
        .join(SourceFile, SourceFile.id == Document.source_file_id)
        .where(CommonRow.user_id == user_id)
    )
    if f.fund:
        stmt = stmt.where(CommonRow.fund_id == int(f.fund) if re.fullmatch(r"[0-9]+", f.fund) else CommonRow.entity.ilike(f"%{f.fund}%"))
    if f.manager:
        stmt = stmt.where(Document.manager.ilike(f"%{f.manager}%"))
    if f.entity_kind:
        stmt = stmt.where(CommonRow.entity_kind == f.entity_kind)
    if f.share_class:
        stmt = stmt.where(CommonRow.share_class == f.share_class)
    if f.measure:
        stmt = stmt.where(CommonRow.measure == f.measure)
    if f.period_kind:
        stmt = stmt.where(CommonRow.period_kind == f.period_kind)
    if f.start:
        stmt = stmt.where(CommonRow.period_end >= f.start)
    if f.end:
        stmt = stmt.where(CommonRow.period_end <= f.end)
    if f.needs_review is not None:
        stmt = stmt.where(CommonRow.needs_review == f.needs_review)
    if f.conflict is not None:
        stmt = stmt.where(CommonRow.conflict == f.conflict)
    if f.document_id is not None:
        stmt = stmt.where(CommonRow.document_id == f.document_id)
    return stmt


def all_rows_query(user_id: int, f: RowFilters) -> Select:
    """Filtered and sorted, not paged (CSV export, one document's rows)."""
    column = _SORTS.get(f.sort, CommonRow.period_end)
    ordered = column.asc() if f.order == "asc" else column.desc()
    return _filtered(user_id, f).order_by(ordered, CommonRow.id)


def rows_query(user_id: int, f: RowFilters) -> Select:
    return all_rows_query(user_id, f).limit(max(1, min(f.limit, MAX_LIMIT))).offset(max(0, f.offset))


def rows_count_query(user_id: int, f: RowFilters) -> Select:
    return select(func.count()).select_from(_filtered(user_id, f).order_by(None).subquery())


def row_json(r) -> dict:
    row: CommonRow = r.CommonRow
    return {
        "id": row.id,
        "document_id": row.document_id,
        "document_name": r.document_name,
        "manager": r.manager,
        "fund_id": row.fund_id,
        "entity": row.entity,
        "entity_kind": row.entity_kind,
        "share_class": row.share_class,
        "measure": row.measure,
        "period_kind": row.period_kind,
        "period_end": row.period_end,
        "value": dec_str(row.value),
        "value_as_written": row.value_as_written,
        "unit": row.unit,
        "currency": row.currency,
        "benchmark_name": row.benchmark_name,
        "table_index": row.table_index,
        "row_index": row.row_index,
        "col_index": row.col_index,
        "needs_review": bool(row.needs_review),
        "review_reason": row.review_reason,
        "conflict": bool(row.conflict),
    }


def rows_csv(rows: list[dict]) -> str:
    """CSV text: `value` is the raw stored decimal string, `value_percent` a display column
    (fractions x 100, only for return measures)."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for r in rows:
        percent = ""
        if r["measure"] in _RETURN_MEASURES:
            percent = dec_str(Decimal(r["value"]) * 100) + "%"
        cells = {**r, "value": r["value"], "value_percent": percent}
        writer.writerow(["" if cells.get(c) is None else cells[c] for c in CSV_COLUMNS])
    return out.getvalue()


def row_filters(
    fund: str | None = None,
    manager: str | None = None,
    entity_kind: str | None = None,
    share_class: str | None = None,
    measure: str | None = None,
    period_kind: str | None = None,
    start: date | None = None,
    end: date | None = None,
    needs_review: bool | None = None,
    conflict: bool | None = None,
    document_id: int | None = Query(
        None, description="Only rows extracted from this document (the id from get_document)."
    ),
    sort: Literal["value", "period_end", "entity"] = "period_end",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(100, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
) -> RowFilters:
    return RowFilters(
        fund, manager, entity_kind, share_class, measure, period_kind, start, end,
        needs_review, conflict, document_id, sort, order, limit, offset,
    )  # fmt: skip


@router.get("/rows", tags=["analyze"], operation_id="query_rows")
def query_rows(
    filters: RowFilters = Depends(row_filters),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> dict:
    """Query extracted numbers (returns, AUM, NAV, ...) with filters, sort and paging.

    Returns {rows, total}. Values are decimal strings; returns are fractions (0.0123 = 1.23%).
    """
    rows = [row_json(r) for r in session.execute(rows_query(user.id, filters)).all()]
    total = session.scalar(rows_count_query(user.id, filters)) or 0
    return {"rows": rows, "total": total}


@router.get("/rows.csv")
def export_rows_csv(
    filters: RowFilters = Depends(row_filters),
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> Response:
    rows = [row_json(r) for r in session.execute(all_rows_query(user.id, filters)).all()]
    return Response(
        rows_csv(rows),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="rows.csv"'},
    )
