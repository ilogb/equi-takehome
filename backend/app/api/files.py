"""File list, retry / re-extract, and original-content streaming."""

import html

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.auth.deps import current_user, user_source
from app.db import get_session
from app.jobs.queue import enqueue
from app.models import CommonRow, Document, SourceFile, User
from app.pipeline.text import eml_part
from app.sources.base import DocumentSource, SourceError

router = APIRouter(prefix="/api")


def files_query(user_id: int, status: str | None = None, q: str | None = None) -> Select:
    """Files of one user with their document metadata and extracted-row count."""
    row_count = (
        select(func.count(CommonRow.id))
        .where(CommonRow.document_id == Document.id, CommonRow.user_id == user_id)
        .correlate(Document)
        .scalar_subquery()
    )
    stmt = (
        select(
            SourceFile.id,
            SourceFile.name,
            SourceFile.path,
            SourceFile.mime_type,
            SourceFile.status,
            SourceFile.error,
            SourceFile.missing_in_drive,
            SourceFile.created_at,
            SourceFile.drive_file_id,
            Document.id.label("document_id"),
            Document.doc_type,
            Document.manager,
            Document.funds,
            Document.as_of_date,
            Document.tags,
            row_count.label("row_count"),
        )
        .select_from(SourceFile)
        .outerjoin(Document, Document.source_file_id == SourceFile.id)
        .where(SourceFile.user_id == user_id)
        .order_by(SourceFile.path, SourceFile.name, SourceFile.id)
    )
    if status:
        stmt = stmt.where(SourceFile.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(SourceFile.name.ilike(like) | SourceFile.path.ilike(like))
    return stmt


def file_kind(mime_type: str, name: str) -> str:
    """Coarse family the UI groups by: pdf, spreadsheet, csv, html, text, image, other."""
    lowered = name.lower()
    if mime_type == "application/pdf" or lowered.endswith(".pdf"):
        return "pdf"
    if mime_type == "text/csv" or lowered.endswith(".csv"):
        return "csv"
    if "spreadsheet" in mime_type or "excel" in mime_type or lowered.endswith((".xlsx", ".xls")):
        return "spreadsheet"
    if mime_type == "text/html" or lowered.endswith((".html", ".htm")):
        return "html"
    if mime_type.startswith("text/"):
        return "text"
    if mime_type.startswith("image/"):
        return "image"
    return "other"


def file_json(row) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "path": row.path,
        "mime_type": row.mime_type,
        "kind": file_kind(row.mime_type, row.name),
        "status": row.status,
        "error": row.error,
        "missing_in_drive": bool(row.missing_in_drive),
        "doc_type": row.doc_type,
        "manager": row.manager,
        "funds": row.funds or [],
        "as_of_date": row.as_of_date,
        "tags": row.tags or [],
        "row_count": row.row_count or 0,
        "updated_at": row.created_at,
        "document_id": row.document_id,
        "drive_file_id": row.drive_file_id,
    }


@router.get("/files")
def list_files(
    status: str | None = None,
    q: str | None = None,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    return [file_json(r) for r in session.execute(files_query(user.id, status, q)).all()]


def _own_file(session: Session, user: User, file_id: int) -> SourceFile:
    file = session.scalar(select(SourceFile).where(SourceFile.id == file_id, SourceFile.user_id == user.id))
    if file is None:
        raise HTTPException(status_code=404, detail="file not found")
    return file


def _requeue(session: Session, user: User, file_id: int) -> dict:
    file = _own_file(session, user, file_id)
    enqueue(session, file.id, force=True)
    session.commit()
    return {"id": file.id, "status": file.status}


@router.post("/files/{file_id}/retry")
def retry_file(
    file_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> dict:
    return _requeue(session, user, file_id)


@router.post("/files/{file_id}/reextract")
def reextract_file(
    file_id: int, user: User = Depends(current_user), session: Session = Depends(get_session)
) -> dict:
    return _requeue(session, user, file_id)


@router.get("/files/{file_id}/content")
def file_content(
    file_id: int,
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
    source: DocumentSource = Depends(user_source),
) -> Response:
    file = _own_file(session, user, file_id)
    is_eml = (
        file.mime_type.split(";")[0].strip().lower() == "message/rfc822"
        or file.name.lower().endswith(".eml")
    )
    chunks = source.stream(file.drive_file_id)
    try:
        # The generator only talks to Drive on first iteration: pull one chunk so a
        # 404 surfaces here, before any response bytes are committed.
        first = next(chunks, b"")
    except SourceError as err:
        if err.status != 404:
            raise
        file.missing_in_drive = True
        session.commit()
        raise HTTPException(status_code=404, detail="No longer in Drive") from None

    if is_eml:
        # Browsers won't render rfc822 in an iframe: serve the extracted body as HTML.
        raw = first + b"".join(chunks)
        body_html, subtype = eml_part(raw)
        if subtype != "html":
            body_html = f"<pre>{html.escape(body_html)}</pre>"
        return Response(
            body_html,
            media_type="text/html; charset=utf-8",
            headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"},
        )

    def body():
        yield first
        yield from chunks

    headers = {"X-Content-Type-Options": "nosniff"}
    if file.mime_type.split(";")[0].strip().lower() != "application/pdf":
        # Anything but a PDF could carry active content (HTML, SVG, ...): no script, own origin.
        headers["Content-Security-Policy"] = "sandbox"
    return StreamingResponse(body(), media_type=file.mime_type, headers=headers)
