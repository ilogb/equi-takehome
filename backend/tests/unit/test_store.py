from datetime import date
from decimal import Decimal
from pathlib import Path

from app.llm.fake import FakeLLM
from app.models import ChunkKind, EntityKind, Measure, PeriodKind
from app.pipeline.detect import FileKind
from app.pipeline.schema import DocumentExtraction, RowOut
from app.pipeline.store import ConflictRow, build_rows, chunk_texts, find_conflicts
from app.pipeline.text import LoadedText

RECORDED = Path(__file__).resolve().parents[1] / "recorded"


def extraction(name: str) -> DocumentExtraction:
    return FakeLLM(RECORDED).extract(file_name=name)


def row(**kw) -> RowOut:
    base = dict(
        entity="Fund A", entity_kind=EntityKind.fund, share_class=None, measure=Measure.return_,
        period_kind=PeriodKind.month, period_end=date(2026, 1, 31), value_as_written="1.0%",
        unit_hint="percent", currency=None, benchmark_name=None,
        table_index=None, row_index=None, col_index=None,
    )
    base.update(kw)
    return RowOut(**base)


def test_man_ahl_jan_return():
    ex = extraction("man-ahl_factsheet_2026-08.pdf")
    assert len(ex.tables) == 18
    drafts = build_rows(ex, ex.as_of_date)
    jan = [
        d for d in drafts
        if d.measure == "return" and d.period_kind == "month" and d.period_end == date(2026, 1, 31)
    ]
    assert Decimal("0.0842") in {d.value for d in jan}


def test_fundsmith_dates_snapped():
    ex = extraction("fundsmith_factsheet_2026-01.pdf")
    drafts = build_rows(ex, ex.as_of_date)
    jan = [
        d for d in drafts
        if d.measure == "return" and d.period_kind == "month" and d.period_end == date(2026, 1, 31)
    ]
    assert Decimal("-0.005") in {d.value for d in jan}
    assert all(d.period_end.day >= 28 for d in drafts if d.period_kind == "month")


def test_harborline_account_rows_only():
    ex = extraction("harborline-custody_account-statement_2026-09.pdf")
    drafts = build_rows(ex, ex.as_of_date)
    assert len(drafts) == 4
    assert all(d.entity_kind == "account" for d in drafts)
    assert not {d.value for d in drafts} & {Decimal("0.217"), Decimal("0.124")}


def test_snaps_period_end_and_skips_placeholders():
    ex = extraction("man-ahl_factsheet_2026-08.pdf").model_copy(
        update={"rows": [row(period_end=date(2026, 1, 15)), row(value_as_written="n/a"),
                         row(value_as_written="garbage")]}
    )
    drafts = build_rows(ex, None)
    assert len(drafts) == 1
    assert drafts[0].period_end == date(2026, 1, 31)
    assert drafts[0].value == Decimal("0.01")
    assert not drafts[0].needs_review


def test_outlier_monthly_return_flagged():
    ex = extraction("fundsmith_factsheet_2026-01.pdf").model_copy(
        update={"rows": [row(value_as_written="62%")]}
    )
    (d,) = build_rows(ex, None)
    assert d.needs_review and d.review_reason == "monthly return beyond ±50%"


def test_period_end_after_as_of_flagged():
    ex = extraction("fundsmith_factsheet_2026-01.pdf").model_copy(
        update={"rows": [row(period_end=date(2026, 3, 31))]}
    )
    (d,) = build_rows(ex, date(2026, 2, 28))
    assert d.needs_review and d.review_reason == "period end after as-of date"


def test_large_ytd_not_flagged():
    ex = extraction("fundsmith_factsheet_2026-01.pdf").model_copy(
        update={"rows": [row(period_kind=PeriodKind.ytd, value_as_written="62%")]}
    )
    (d,) = build_rows(ex, None)
    assert not d.needs_review


def cr(id, doc, value, entity="Fund A", share_class=None):
    return ConflictRow(
        id=id, document_id=doc, entity=entity, share_class=share_class, measure="return",
        period_kind="month", period_end=date(2026, 1, 31), value=Decimal(value),
    )


def test_conflict_flags_both():
    assert find_conflicts([cr(1, 1, "0.0237"), cr(2, 2, "0.0235")]) == {1, 2}


def test_within_tolerance_no_conflict():
    assert find_conflicts([cr(1, 1, "0.02370"), cr(2, 2, "0.02373")]) == set()


def test_share_classes_not_conflicts():
    rows = [cr(1, 1, "0.0312", "Alderbank", "A EUR Acc"), cr(2, 2, "0.0321", "Alderbank", "I EUR Acc")]
    assert find_conflicts(rows) == set()


def test_entity_spelling_variants_match():
    rows = [cr(1, 1, "0.0237", "Northwind Global Macro Fund, L.P."), cr(2, 2, "0.0235", "Northwind Global Macro LP")]
    assert find_conflicts(rows) == {1, 2}


def test_same_document_never_conflicts():
    assert find_conflicts([cr(1, 1, "0.0237"), cr(2, 1, "0.0235")]) == set()


def test_chunks_without_tables_or_rows():
    ex = extraction("fundsmith_factsheet_2026-01.pdf").model_copy(update={"tables": [], "rows": []})
    text = LoadedText(FileKind.__args__[0], ["page one text", "page two text"])
    chunks = chunk_texts(text, ex.tables, ex)
    kinds = [k for k, _ in chunks]
    assert kinds.count(ChunkKind.page) == 2 and kinds.count(ChunkKind.card) == 1
    assert ChunkKind.table not in kinds


def test_long_page_split_and_tables_rendered():
    ex = extraction("harborline-custody_account-statement_2026-09.pdf")
    page = "\n".join(f"line {i} " + "word " * 40 for i in range(60))
    chunks = chunk_texts(LoadedText("pdf", [page, "   "]), ex.tables, ex)
    pages = [t for k, t in chunks if k == ChunkKind.page]
    assert len(pages) > 1 and all(t.strip() for t in pages)
    tables = [t for k, t in chunks if k == ChunkKind.table]
    assert len(tables) == len(ex.tables)
    assert " | " in tables[0]
