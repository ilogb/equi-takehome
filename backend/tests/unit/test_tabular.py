import io
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

import pandas as pd

from app.models import EntityKind, Measure, PeriodKind
from app.pipeline.schema import CsvMapping, PeriodSpec
from app.pipeline.tabular import RawTable, apply_mapping, read_tables
from app.values import parse_value

ROOT = Path(__file__).resolve().parents[3]
RECORDED = Path(__file__).resolve().parents[1] / "recorded"
NORTHWIND = ROOT / "fixtures/synthetic/northwind-capital_monthly-returns_2026-09.csv"
ALDERBANK = ROOT / "fixtures/synthetic/alderbank_performance-summary_2026-09.csv"
TSP = ROOT / "fixtures/real/tsp_nav-history_2026-10.csv"


def _mapping(name: str) -> CsvMapping:
    return CsvMapping.model_validate_json((RECORDED / name).read_text())


def _table(path: Path) -> RawTable:
    (table,) = read_tables(path.read_bytes(), "csv", path.name)
    return table


def test_northwind_long():
    table = _table(NORTHWIND)
    rows = apply_mapping(
        table, _mapping("map_northwind-capital_monthly-returns_2026-09.json"), 0
    )
    assert len(rows) == 35
    july = [r for r in rows if r.period_end == date(2026, 7, 31) and r.share_class == "Founders"]
    assert {r.entity for r in july} == {"Northwind Global Macro Fund LP"}
    credit = [r for r in rows if r.entity == "Northwind Credit Opportunities Fund"]
    may_ret = [r for r in credit if r.period_end == date(2026, 5, 31) and r.measure == Measure.return_]
    assert may_ret == []
    may_bench = [
        r for r in credit if r.period_end == date(2026, 5, 31) and r.measure == Measure.benchmark_return
    ]
    assert len(may_bench) == 1
    assert may_bench[0].benchmark_name == "ICE BofA US High Yield Index"
    assert may_bench[0].value_as_written == "0.20"
    first = rows[0]
    assert first.entity == "Northwind Global Macro Fund, L.P."
    assert first.entity_kind == EntityKind.fund
    assert first.share_class == "Founders"
    assert first.period_kind == PeriodKind.month
    assert first.period_end == date(2026, 1, 31)
    assert (first.table_index, first.row_index, first.col_index) == (0, 1, 3)
    assert first.unit_hint == "percent"
    assert first.benchmark_name is None
    assert parse_value(first.value_as_written, first.unit_hint).value == Decimal("0.0237")


def test_alderbank_wide():
    table = _table(ALDERBANK)
    rows = apply_mapping(
        table, _mapping("map_alderbank_performance-summary_2026-09.json"), 0
    )
    assert len(rows) == 29
    assert {(r.entity, r.share_class) for r in rows} >= {
        ("Alderbank European Equity Fund", "A EUR Acc"),
        ("Alderbank European Equity Fund", "I EUR Acc"),
    }
    asia_ytd = next(
        r for r in rows
        if r.entity == "Alderbank Asia Income Fund" and r.period_kind == PeriodKind.ytd
    )
    assert asia_ytd.period_end == date(2026, 8, 31)
    assert asia_ytd.value_as_written == "3.87%*"
    assert parse_value(asia_ytd.value_as_written, "percent").value == Decimal("0.0387")
    euro_ytd = next(
        r for r in rows
        if r.share_class == "I EUR Acc" and r.period_kind == PeriodKind.ytd
    )
    assert euro_ytd.period_end == date(2026, 9, 30)
    jan = next(r for r in rows if r.period_kind == PeriodKind.month and r.col_index == 2)
    assert jan.period_end == date(2026, 1, 31)
    assert jan.row_index == 4
    assert not any(
        r.entity == "Alderbank Asia Income Fund" and r.period_end == date(2026, 9, 30) for r in rows
    )


def test_xlsx_two_sheets():
    table = _table(NORTHWIND)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pd.DataFrame(table.cells).to_excel(xw, sheet_name="Returns", header=False, index=False)
        pd.DataFrame([["Note", "x"]]).to_excel(xw, sheet_name="Notes", header=False, index=False)
    tables = read_tables(buf.getvalue(), "xlsx", "book.xlsx")
    assert [t.name for t in tables] == ["Returns", "Notes"]
    assert tables[0].cells[0][:3] == ["Fund", "Share Class", "Period"]
    assert tables[0].cells[1][3] == "2.37"
    rows = apply_mapping(
        tables[0], _mapping("map_northwind-capital_monthly-returns_2026-09.json"), 0
    )
    assert len(rows) == 35


def test_csv_bom_stripped():
    (table,) = read_tables("﻿a,b\n1,2\n".encode(), "csv", "x.csv")
    assert table.cells == [["a", "b"], ["1", "2"]]


def test_tsp_size():
    table = _table(TSP)
    funds = table.cells[0][1:]
    assert len(funds) == 16
    mapping = CsvMapping(
        layout="entity_columns",
        skip_top=0,
        skip_bottom=0,
        entity_column=None,
        constant_entity=None,
        share_class_column=None,
        date_column="Date",
        period_columns=funds,
        period_spec=PeriodSpec(
            measure=Measure.nav, period_kind=PeriodKind.other, unit_hint="number",
            benchmark_name=None,
        ),
        benchmark_column=None,
        value_columns=[],
        date_format=None,
        period_end_overrides=[],
    )
    expected = sum(1 for r in table.cells[1:] for c in r[1:] if c.strip())
    start = time.monotonic()
    rows = apply_mapping(table, mapping, 0)
    assert time.monotonic() - start < 20
    assert len(rows) == expected
    first = rows[0]
    assert (first.entity, first.period_end, first.value_as_written) == (
        "L Income", date(2026, 10, 27), "31.1208",
    )
    assert first.measure == Measure.nav and first.period_kind == PeriodKind.other
    assert (first.row_index, first.col_index) == (1, 1)
    c_fund = next(r for r in rows if r.entity == "C Fund" and r.period_end == date(2026, 10, 26))
    assert c_fund.value_as_written == "123.9318"


def _mapping_with(**changes) -> CsvMapping:
    base = _mapping("map_alderbank_performance-summary_2026-09.json")
    return base.model_copy(update=changes)


def test_wide_without_period_spec_and_columns_yields_nothing():
    table = _table(ALDERBANK)
    m = _mapping_with(period_spec=None, period_columns=[], value_columns=[])
    assert apply_mapping(table, m, 0) == []


def test_wide_with_period_columns_but_no_spec_is_an_error():
    import pytest

    with pytest.raises(ValueError, match="period_spec"):
        apply_mapping(_table(ALDERBANK), _mapping_with(period_spec=None), 0)


def test_wide_with_only_empty_columns_yields_nothing():
    table = _table(ALDERBANK)
    assert apply_mapping(table, _mapping_with(period_columns=[], value_columns=[]), 0) == []


def test_all_blank_body_yields_nothing():
    table = RawTable("t", [["Fund", "Jan-26"], ["", ""], ["", ""]])
    m = _mapping_with(skip_top=0, skip_bottom=0, period_columns=["Jan-26"], value_columns=[],
                      share_class_column=None, period_end_overrides=[])
    assert apply_mapping(table, m, 0) == []
