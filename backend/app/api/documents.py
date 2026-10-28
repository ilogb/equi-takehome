"""One document: metadata, printed tables, extracted rows."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.files import file_kind
from app.api.rows import RowFilters, row_json, rows_count_query, rows_query
from app.auth.deps import current_user
from app.db import get_session
from app.models import Document, PrintedTable, SourceFile, User

router = APIRouter(prefix="/api")

DOCUMENT_ROWS_LIMIT = 500
TABLE_ROWS_LIMIT = 200


def table_json(t: PrintedTable) -> dict:
    """A printed table with its body capped at ``TABLE_ROWS_LIMIT`` rows."""
    rows = t.rows or []
    return {
        "index": t.index,
        "title": t.title,
        "header": t.header,
        "rows": rows[:TABLE_ROWS_LIMIT],
        "rows_total": len(rows),
    }


@router.get("/documents/{document_id}", tags=["analyze"], operation_id="get_document")
def get_document(
    document_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> dict:
    """Fetch one document: its metadata, the tables printed in it, and the rows extracted from it.

    The `file` object carries the source file's status, error and Drive details. At most 500
    rows are returned (`rows_total` is the full count; page through the rest with query_rows
    and `document_id`), and each printed table carries at most its first 200 body rows
    (`rows_total` per table is the full count)."""
    found = session.execute(
        select(Document, SourceFile)
        .join(SourceFile, SourceFile.id == Document.source_file_id)
        .where(Document.id == document_id, Document.user_id == user.id)
    ).first()
    if found is None:
        raise HTTPException(status_code=404, detail="document not found")
    doc, file = found
    tables = session.scalars(
        select(PrintedTable)
        .where(PrintedTable.document_id == doc.id, PrintedTable.user_id == user.id)
        .order_by(PrintedTable.index)
    ).all()
    filters = RowFilters(document_id=doc.id, sort="period_end", order="asc", limit=DOCUMENT_ROWS_LIMIT)
    rows = session.execute(rows_query(user.id, filters)).all()
    rows_total = session.scalar(rows_count_query(user.id, filters)) or 0
    return {
        "id": doc.id,
        "source_file_id": file.id,
        "name": file.name,
        "path": file.path,
        "mime_type": file.mime_type,
        "status": file.status,
        "doc_type": doc.doc_type,
        "manager": doc.manager,
        "as_of_date": doc.as_of_date,
        "currency": doc.currency,
        "summary": doc.summary,
        "tags": doc.tags or [],
        "funds": doc.funds or [],
        "file": {
            "id": file.id,
            "status": file.status,
            "error": file.error,
            "missing_in_drive": bool(file.missing_in_drive),
            "mime_type": file.mime_type,
            "kind": file_kind(file.mime_type, file.name),
            "path": file.path,
            "name": file.name,
            "drive_file_id": file.drive_file_id,
        },
        "tables": [table_json(t) for t in tables],
        "rows": [row_json(r) for r in rows],
        "rows_total": rows_total,
    }
