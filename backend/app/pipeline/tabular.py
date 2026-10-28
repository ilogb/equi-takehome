"""CSV and .xlsx files: raw string tables, and an LLM-produced CsvMapping applied with pandas."""

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

import pandas as pd

from app.models import EntityKind, Measure, PeriodKind
from app.pipeline.schema import CsvMapping, RowOut, UnitHint
from app.values import parse_value, snap_period_end

__all__ = ["RawTable", "apply_mapping", "read_tables"]


@dataclass(frozen=True)
class RawTable:
    name: str
    cells: list[list[str]]


def _pad(rows: list[list[str]]) -> list[list[str]]:
    width = max((len(r) for r in rows), default=0)
    return [r + [""] * (width - len(r)) for r in rows]


def read_tables(data: bytes, kind: Literal["csv", "xlsx"], name: str) -> list[RawTable]:
    if kind == "csv":
        text = data.decode("utf-8-sig")
        return [RawTable(name, _pad([list(r) for r in csv.reader(io.StringIO(text))]))]
    sheets = pd.read_excel(
        io.BytesIO(data), sheet_name=None, header=None, dtype=str, keep_default_na=False
    )
    return [
        RawTable(str(sheet), df.astype(str).values.tolist()) for sheet, df in sheets.items()
    ]


@dataclass(frozen=True)
class _Spec:
    measure: Measure
    period_kind: PeriodKind
    unit_hint: UnitHint
    benchmark_name: str | None


def _parse_date(text: str, fmt: str | None) -> date | None:
    text = text.strip()
    if not text:
        return None
    try:
        if fmt:
            return datetime.strptime(text, fmt).date()
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def apply_mapping(table: RawTable, mapping: CsvMapping, table_index: int) -> list[RowOut]:
    cells = table.cells
    if mapping.skip_top >= len(cells):
        return []
    header = [h.strip() for h in cells[mapping.skip_top]]
    first = mapping.skip_top + 1
    last = len(cells) - mapping.skip_bottom
    body = cells[first:last]
    if not body:
        return []

    def pos(column: str) -> int:
        try:
            return header.index(column.strip())
        except ValueError:
            raise ValueError(f"mapped column {column!r} not in header {header}") from None

    df = pd.DataFrame(body, dtype=str)
    df.index = range(first, first + len(df))
    df = df[(df != "").any(axis=1)]
    df.index.name = "row"

    ent = pos(mapping.entity_column) if mapping.entity_column else None
    cls = pos(mapping.share_class_column) if mapping.share_class_column else None
    bench = pos(mapping.benchmark_column) if mapping.benchmark_column else None
    date_col = pos(mapping.date_column) if mapping.date_column else None
    fmt = mapping.date_format

    # column position -> (spec, fixed period end from the column header, if any)
    specs: dict[int, tuple[_Spec, date | None]] = {}
    period_dates: list[date] = []
    if mapping.layout == "wide" and mapping.period_spec:
        ps = mapping.period_spec
        spec = _Spec(ps.measure, ps.period_kind, ps.unit_hint, ps.benchmark_name)
        for col in mapping.period_columns:
            d = _parse_date(col, fmt)
            if d is None:
                raise ValueError(f"period column {col!r} is not a date")
            end = snap_period_end(d, ps.period_kind)
            specs[pos(col)] = (spec, end)
            period_dates.append(end)
    latest = max(period_dates) if period_dates else None
    for vc in mapping.value_columns:
        spec = _Spec(vc.measure, vc.period_kind, vc.unit_hint, vc.benchmark_name)
        specs[pos(vc.column)] = (spec, None)

    overrides = {(o.entity, o.period_kind): o.period_end for o in mapping.period_end_overrides}
    # melt to one record per (source row, value column), then walk the records
    long = df.reset_index().melt(
        id_vars="row", value_vars=[c for c in specs if c in df.columns], var_name="col",
        value_name="cell",
    )
    long = long[long["cell"].str.strip() != ""].sort_values(["row", "col"], kind="stable")
    by_row = df.to_dict("index")
    date_cache: dict[str, date | None] = {}
    out: list[RowOut] = []
    for row, col, cell in long.itertuples(index=False):
        rec = by_row[row]
        entity = rec[ent].strip() if ent is not None else (mapping.constant_entity or "")
        if not entity:
            continue
        spec, fixed_end = specs[col]
        if fixed_end is not None:
            end = fixed_end
        elif date_col is not None:
            raw = rec[date_col]
            if raw not in date_cache:
                date_cache[raw] = _parse_date(raw, fmt)
            d = date_cache[raw]
            if d is None:
                continue
            end = snap_period_end(d, spec.period_kind)
        elif latest is not None:
            end = latest
        else:
            continue
        end = overrides.get((entity, spec.period_kind), end)
        written = cell.strip()
        parsed = parse_value(written.rstrip("*").strip(), spec.unit_hint)
        if parsed is None:
            continue
        name = spec.benchmark_name
        if name is None and bench is not None and spec.measure == Measure.benchmark_return:
            name = rec[bench].strip() or None
        out.append(
            RowOut(
                entity=entity,
                entity_kind=EntityKind.fund,
                share_class=(rec[cls].strip() or None) if cls is not None else None,
                measure=spec.measure,
                period_kind=spec.period_kind,
                period_end=end,
                value_as_written=written,
                unit_hint=spec.unit_hint,
                currency=parsed.currency,
                benchmark_name=name,
                table_index=table_index,
                row_index=row,
                col_index=col,
            )
        )
    return out
