"""One document: metadata, printed tables, extracted rows."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.files import file_kind
from app.api.rows import RowFilters, all_rows_query, row_json
from app.auth.deps import current_user
from app.db import get_session
from app.models import Document, PrintedTable, SourceFile, User

router = APIRouter(prefix="/api")


@router.get("/documents/{document_id}", tags=["analyze"], operation_id="get_document")
def get_document(
    document_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> dict:
    """Fetch one document: its metadata, the tables printed in it, and every row extracted from it.

    The `file` object carries the source file's status, error and Drive details."""
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
    filters = RowFilters(document_id=doc.id, sort="period_end", order="asc")
    rows = session.execute(all_rows_query(user.id, filters)).all()
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
        "tables": [{"index": t.index, "title": t.title, "header": t.header, "rows": t.rows} for t in tables],
        "rows": [row_json(r) for r in rows],
    }
