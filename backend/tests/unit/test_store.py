from datetime import date
from decimal import Decimal
from pathlib import Path

from app.llm.fake import FakeLLM
from app.models import ChunkKind, EntityKind, Measure, PeriodKind
from app.pipeline.detect import FileKind
from app.pipeline.schema import DocumentExtraction, RowOut, TableOut
from app.pipeline.store import (
    MAX_EMBED_TOKENS,
    ConflictRow,
    build_rows,
    chunk_texts,
    conflict_changes,
    estimate_tokens,
    find_conflicts,
    mark_conflicts,
)
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


def test_huge_table_split_with_title_and_header_on_every_piece():
    header = [["Date", "G Fund", "F Fund", "C Fund", "S Fund", "I Fund"]]
    rows = [[f"2004-01-{i:05d}", "13.2345", "10.1234", "12.3456", "14.5678", "11.2345"] for i in range(5000)]
    table = TableOut(title="TSP share prices", header=header, rows=rows)
    ex = extraction("fundsmith_factsheet_2026-01.pdf").model_copy(update={"tables": [table], "rows": []})
    chunks = chunk_texts(LoadedText("csv", []), ex.tables, ex)
    tables = [t for k, t in chunks if k == ChunkKind.table]
    assert len(tables) > 10
    for t in tables:
        lines = t.splitlines()
        assert lines[0] == "TSP share prices"
        assert lines[1] == "Date | G Fund | F Fund | C Fund | S Fund | I Fund"
        assert estimate_tokens(t) <= 1000
    body = [line for t in tables for line in t.splitlines()[2:]]
    assert len(body) == 5000  # every row lands in exactly one piece
    assert all(estimate_tokens(t) <= MAX_EMBED_TOKENS for _, t in chunks)


def test_no_chunk_exceeds_embed_limit_even_without_spaces():
    ex = extraction("fundsmith_factsheet_2026-01.pdf").model_copy(
        update={"tables": [], "rows": [], "summary": "x" * 100_000}
    )
    chunks = chunk_texts(LoadedText("pdf", ["y" * 100_000]), ex.tables, ex)
    assert all(estimate_tokens(t) <= MAX_EMBED_TOKENS for _, t in chunks)
    assert sum(len(t) for k, t in chunks if k == ChunkKind.page) == 100_000


def test_conflict_changes_only_touches_rows_that_flip():
    current = {1: False, 2: True, 3: True, 4: False}
    turn_on, turn_off = conflict_changes(current, {1, 2})
    assert turn_on == {1}
    assert turn_off == {3}


def test_conflict_changes_no_op_when_unchanged():
    assert conflict_changes({1: True, 2: False}, {1}) == (set(), set())


class _RecordingSession:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    def execute(self, stmt, params=None):
        self.statements.append((stmt, params))
        return self

    def all(self):
        return self.rows

    def flush(self):
        pass


def test_mark_conflicts_takes_advisory_lock_and_writes_only_changes():
    def full(id, doc, value, conflict):
        c = cr(id, doc, value)
        return (c.id, c.document_id, c.entity, c.share_class, c.measure, c.period_kind,
                c.period_end, c.value, conflict)

    session = _RecordingSession([full(1, 1, "0.0237", False), full(2, 2, "0.0235", True),
                                 full(3, 3, "0.0500", True)])
    # all three share an identity and differ, so all are flagged; only row 1 changes
    flagged = mark_conflicts(session, user_id=7)
    lock_stmt, lock_params = session.statements[0]
    assert "pg_advisory_xact_lock(:user_id)" in str(lock_stmt)
    assert lock_params == {"user_id": 7}
    assert flagged == 3
    updates = [str(s) for s, _ in session.statements[2:]]
    assert len(updates) == 1 and "UPDATE common_row" in updates[0]
    params = session.statements[2][0].compile().params
    assert params["conflict"] is True and [1] in params.values()
