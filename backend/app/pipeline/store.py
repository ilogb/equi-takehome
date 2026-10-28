"""Persist a validated extraction: documents, printed tables, common rows and chunks.

The logic lives in pure functions (``build_rows``, ``find_conflicts``,
``chunk_texts``); ``persist_extraction`` and ``mark_conflicts`` are thin database
wrappers around them.
"""

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.llm.base import PROMPT_VERSION, LLMProvider
from app.models import (
    Chunk,
    ChunkKind,
    CommonRow,
    Document,
    EntityKind,
    FileStatus,
    Measure,
    PeriodKind,
    PrintedTable,
    SourceFile,
)
from app.pipeline.funds import fund_key, resolve_fund
from app.pipeline.schema import DocumentExtraction, TableOut
from app.pipeline.text import LoadedText
from app.values import parse_value, snap_period_end

CONFLICT_TOLERANCE = Decimal("0.00005")
MONTHLY_RETURN_LIMIT = Decimal("0.5")
REASON_OUTLIER = "monthly return beyond ±50%"
REASON_AFTER_AS_OF = "period end after as-of date"
CHUNK_TOKENS = 800
TOKENS_PER_WORD = 1.3  # approximation: tokens ~= words x 1.3
EMBED_BATCH = 64
_RETURN_MEASURES = {Measure.return_, Measure.benchmark_return, Measure.account_return}


@dataclass(frozen=True)
class RowDraft:
    entity: str
    entity_kind: str
    share_class: str | None
    measure: str
    period_kind: str
    period_end: date
    value: Decimal
    value_as_written: str
    unit: str
    currency: str | None
    benchmark_name: str | None
    table_index: int | None
    row_index: int | None
    col_index: int | None
    needs_review: bool
    review_reason: str | None


def build_rows(ex: DocumentExtraction, as_of: date | None) -> list[RowDraft]:
    """Parse, snap and check the extracted rows; unparseable or placeholder cells are dropped."""
    drafts: list[RowDraft] = []
    for r in ex.rows:
        parsed = parse_value(r.value_as_written, r.unit_hint)
        if parsed is None:
            continue
        period_end = snap_period_end(r.period_end, r.period_kind)
        reason = None
        if (
            r.measure in _RETURN_MEASURES
            and r.period_kind == PeriodKind.month
            and abs(parsed.value) > MONTHLY_RETURN_LIMIT
        ):
            reason = REASON_OUTLIER
        elif as_of is not None and period_end > as_of:
            reason = REASON_AFTER_AS_OF
        drafts.append(
            RowDraft(
                entity=r.entity,
                entity_kind=r.entity_kind.value,
                share_class=r.share_class,
                measure=r.measure.value,
                period_kind=r.period_kind.value,
                period_end=period_end,
                value=parsed.value,
                value_as_written=r.value_as_written,
                unit=parsed.unit,
                currency=parsed.currency or r.currency,
                benchmark_name=r.benchmark_name,
                table_index=r.table_index,
                row_index=r.row_index,
                col_index=r.col_index,
                needs_review=reason is not None,
                review_reason=reason,
            )
        )
    return drafts


@dataclass(frozen=True)
class ConflictRow:
    id: int
    document_id: int
    entity: str
    share_class: str | None
    measure: str
    period_kind: str
    period_end: date
    value: Decimal


def find_conflicts(rows: Iterable[ConflictRow]) -> set[int]:
    """Ids of rows whose value differs from another document's for the same identity."""
    groups: dict[tuple, list[ConflictRow]] = defaultdict(list)
    for r in rows:
        key = (
            fund_key(r.entity),
            (r.share_class or "").strip().lower(),
            r.measure,
            r.period_kind,
            r.period_end,
        )
        groups[key].append(r)
    flagged: set[int] = set()
    for group in groups.values():
        for i, a in enumerate(group):
            for b in group[i + 1 :]:
                if a.document_id != b.document_id and abs(a.value - b.value) > CONFLICT_TOLERANCE:
                    flagged.update((a.id, b.id))
    return flagged


def _split_by_tokens(text: str, limit: int = CHUNK_TOKENS) -> list[str]:
    """Split on line boundaries into pieces of about ``limit`` tokens (words x 1.3)."""
    max_words = int(limit / TOKENS_PER_WORD)
    pieces: list[str] = []
    current: list[str] = []
    count = 0
    for line in text.splitlines():
        words = line.split()
        if not words:
            continue
        for start in range(0, len(words), max_words):  # a single huge line is cut by words
            part = words[start : start + max_words]
            if current and count + len(part) > max_words:
                pieces.append("\n".join(current))
                current, count = [], 0
            current.append(" ".join(part))
            count += len(part)
    if current:
        pieces.append("\n".join(current))
    return pieces


def _table_text(t: TableOut) -> str:
    lines = [t.title] if t.title else []
    lines += [" | ".join(r) for r in (*t.header, *t.rows)]
    return "\n".join(lines)


def _card_text(ex: DocumentExtraction) -> str:
    parts = [
        f"Document type: {ex.doc_type.value}",
        f"Manager: {ex.manager}" if ex.manager else "",
        f"As of: {ex.as_of_date.isoformat()}" if ex.as_of_date else "",
        f"Currency: {ex.currency}" if ex.currency else "",
        "Funds: " + "; ".join(f"{f.name} ({f.share_class})" if f.share_class else f.name for f in ex.funds)
        if ex.funds
        else "",
        "Tags: " + ", ".join(ex.tags) if ex.tags else "",
        ex.summary,
    ]
    return "\n".join(p for p in parts if p)


def chunk_texts(
    text: LoadedText, tables: Sequence[TableOut], ex: DocumentExtraction
) -> list[tuple[ChunkKind, str]]:
    """Page pieces (~800 tokens), one chunk per printed table, then one metadata card."""
    chunks: list[tuple[ChunkKind, str]] = []
    for page in text.pages:
        chunks += [(ChunkKind.page, piece) for piece in _split_by_tokens(page)]
    for t in tables:
        body = _table_text(t)
        if body.strip():
            chunks.append((ChunkKind.table, body))
    chunks.append((ChunkKind.card, _card_text(ex)))
    return chunks


def persist_extraction(
    session: Session,
    file: SourceFile,
    text: LoadedText,
    ex: DocumentExtraction,
    llm: LLMProvider,
    model: str,
) -> Document:
    """Replace the file's document with one built from ``ex`` and set the file status."""
    old = session.scalar(select(Document).where(Document.source_file_id == file.id))
    if old is not None:
        session.delete(old)
        session.flush()

    doc = Document(
        user_id=file.user_id,
        source_file_id=file.id,
        doc_type=ex.doc_type.value,
        manager=ex.manager,
        as_of_date=ex.as_of_date,
        currency=ex.currency,
        summary=ex.summary,
        tags=ex.tags,
        funds=[f.model_dump() for f in ex.funds],
        page_texts=text.pages,
        model=model,
        prompt_version=PROMPT_VERSION,
    )
    session.add(doc)
    session.flush()

    for i, t in enumerate(ex.tables):
        session.add(
            PrintedTable(
                user_id=file.user_id, document_id=doc.id, index=i,
                title=t.title, header=t.header, rows=t.rows,
            )
        )

    drafts = build_rows(ex, ex.as_of_date)
    fund_ids: dict[str, int] = {}
    for d in drafts:
        fund_id = None
        if d.entity_kind == EntityKind.fund.value:
            if d.entity not in fund_ids:
                fund_ids[d.entity] = resolve_fund(session, file.user_id, d.entity, ex.manager).id
            fund_id = fund_ids[d.entity]
        session.add(
            CommonRow(
                user_id=file.user_id, document_id=doc.id, fund_id=fund_id,
                entity=d.entity, entity_kind=d.entity_kind, share_class=d.share_class,
                measure=d.measure, period_kind=d.period_kind, period_end=d.period_end,
                value=d.value, value_as_written=d.value_as_written, unit=d.unit,
                currency=d.currency, benchmark_name=d.benchmark_name,
                table_index=d.table_index, row_index=d.row_index, col_index=d.col_index,
                needs_review=d.needs_review, review_reason=d.review_reason,
            )
        )

    chunks = chunk_texts(text, ex.tables, ex)
    for start in range(0, len(chunks), EMBED_BATCH):
        batch = chunks[start : start + EMBED_BATCH]
        vectors = llm.embed([t for _, t in batch])
        for (kind, body), vec in zip(batch, vectors, strict=True):
            session.add(
                Chunk(user_id=file.user_id, document_id=doc.id, kind=kind.value, text=body, embedding=vec)
            )

    file.status = (
        FileStatus.needs_review.value if any(d.needs_review for d in drafts) else FileStatus.done.value
    )
    file.error = None
    session.flush()
    return doc


def mark_conflicts(session: Session, user_id: int) -> int:
    """Recompute ``common_row.conflict`` for the user; returns the number of flagged rows."""
    rows = session.execute(
        select(
            CommonRow.id, CommonRow.document_id, CommonRow.entity, CommonRow.share_class,
            CommonRow.measure, CommonRow.period_kind, CommonRow.period_end, CommonRow.value,
        ).where(CommonRow.user_id == user_id)
    ).all()
    flagged = find_conflicts(ConflictRow(*r) for r in rows)
    session.execute(
        update(CommonRow).where(CommonRow.user_id == user_id).values(conflict=False)
    )
    if flagged:
        session.execute(update(CommonRow).where(CommonRow.id.in_(flagged)).values(conflict=True))
    session.flush()
    return len(flagged)
