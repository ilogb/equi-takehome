"""Process one Drive file: download, detect, then scanned / unsupported / extract, and persist."""

from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.llm.base import LLMProvider
from app.models import Document, FileStatus, SourceFile
from app.pipeline.detect import FileKind, is_scanned, kind_for
from app.pipeline.funds import known_fund_names
from app.pipeline.schema import DocumentExtraction, TableOut
from app.pipeline.store import mark_conflicts, persist_extraction
from app.pipeline.tabular import RawTable, apply_mapping, read_tables
from app.pipeline.text import LoadedText, TooManyPages, load_text
from app.sources.base import DocumentSource

TOO_MANY_PAGES = "PDF has more than 50 pages"
HEAD_ROWS = 20
TAIL_ROWS = 5
METADATA_LINES = 40

Route = Literal["unsupported", "failed", "scanned", "pdf", "text", "tabular"]


@dataclass(frozen=True)
class Plan:
    """What to do with a downloaded file; computed without touching the database or the LLM."""

    route: Route
    error: str | None = None
    text: LoadedText | None = None
    tables: list[RawTable] | None = None


def plan_processing(kind: FileKind | None, data: bytes, name: str = "") -> Plan:
    if kind is None:
        return Plan("unsupported", "Unsupported file type")
    try:
        if kind in ("csv", "xlsx"):
            return Plan("tabular", tables=read_tables(data, kind, name))
        text = load_text(data, kind)
    except TooManyPages:
        return Plan("unsupported", TOO_MANY_PAGES)
    except Exception as exc:  # corrupt files raise arbitrary parser errors; retrying won't help
        return Plan("failed", f"Could not read file: {type(exc).__name__}: {exc}"[:500])
    if kind == "pdf":
        return Plan("scanned" if is_scanned(text.pages) else "pdf", text=text)
    return Plan("text", text=text)


def csv_head_tail(cells: list[list[str]]) -> tuple[list[list[str]], list[list[str]]]:
    """Rows shown to the mapping model: leading blank rows (skip) + 20 rows, then the last 5.

    The tail never overlaps the head.
    """
    skip = 0
    while skip < len(cells) and not any(c.strip() for c in cells[skip]):
        skip += 1
    head = cells[: skip + HEAD_ROWS]
    tail = cells[len(head) :][-TAIL_ROWS:]
    return head, tail


def metadata_text(tables: list[RawTable]) -> str:
    """First 40 lines of the first table, as comma-joined rows, for the metadata call."""
    lines = [",".join(row) for row in tables[0].cells[:METADATA_LINES]] if tables else []
    return "\n".join(lines).replace("\x00", "")


def extract_tabular(
    file_name: str, tables: list[RawTable], llm: LLMProvider, known_funds: list[str]
) -> DocumentExtraction:
    """Metadata from a small extract call (its rows/tables ignored); rows from mapping each table."""
    meta = llm.extract(
        file_name=file_name, pdf=None, text=metadata_text(tables), known_funds=known_funds
    )
    rows = []
    for i, table in enumerate(tables):
        head, tail = csv_head_tail(table.cells)
        mapping = llm.map_table(name=table.name, head=head, tail=tail)
        rows += apply_mapping(table, mapping, i)
    printed = [
        TableOut(
            title=t.name, header=[],
            rows=[[c.replace("\x00", "") for c in row] for row in t.cells],
        )
        for t in tables
    ]
    return meta.model_copy(update={"rows": rows, "tables": printed})


def _store_page_text(session: Session, file: SourceFile, text: LoadedText) -> None:
    old = session.scalar(select(Document).where(Document.source_file_id == file.id))
    if old is not None:
        session.delete(old)
        session.flush()
    session.add(
        Document(user_id=file.user_id, source_file_id=file.id, page_texts=text.pages, tags=[], funds=[])
    )


def _finish(session: Session, file: SourceFile, status: FileStatus, error: str | None) -> FileStatus:
    file.status = status.value
    file.error = error
    session.flush()
    return status


def process_file(
    session: Session,
    file: SourceFile,
    source: DocumentSource,
    llm: LLMProvider,
    settings: Settings,
) -> FileStatus:
    """Run one file through the pipeline and return its final status.

    ``LLMError`` propagates for the queue to retry. Problems with the file itself become
    statuses (unsupported / scanned_no_text / failed).
    """
    data = source.download(file.drive_file_id)
    kind = kind_for(file.mime_type, file.name)
    plan = plan_processing(kind, data, file.name)

    if plan.route == "unsupported":
        error = plan.error if kind is not None else f"Unsupported file type: {file.mime_type}"
        return _finish(session, file, FileStatus.unsupported, error)
    if plan.route == "failed":
        return _finish(session, file, FileStatus.failed, plan.error)
    if plan.route == "scanned":
        assert plan.text is not None
        _store_page_text(session, file, plan.text)
        return _finish(session, file, FileStatus.scanned_no_text, None)

    known = known_fund_names(session, file.user_id)
    if plan.route == "tabular":
        assert plan.tables is not None and kind is not None
        try:
            ex = extract_tabular(file.name, plan.tables, llm, known)
        except ValueError as exc:  # the mapping names a column the file lacks
            return _finish(session, file, FileStatus.failed, f"Could not map table: {exc}"[:500])
        loaded = LoadedText(kind, [])
        model = settings.mapping_model
    else:
        assert plan.text is not None
        loaded = plan.text
        if plan.route == "pdf":
            ex = llm.extract(file_name=file.name, pdf=data, text=None, known_funds=known)
        else:
            ex = llm.extract(file_name=file.name, pdf=None, text=loaded.pages[0], known_funds=known)
        model = settings.extraction_model

    persist_extraction(session, file, loaded, ex, llm, model)
    mark_conflicts(session, file.user_id)
    return FileStatus(file.status)
