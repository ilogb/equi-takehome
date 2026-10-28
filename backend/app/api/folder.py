"""Folder selection and sync routes."""

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.deps import auth_settings, current_user, user_source
from app.auth.google import drive_source_for
from app.config import Settings
from app.db import get_session
from app.models import SourceFile, User, WatchedFolder
from app.sources.base import DocumentSource, SourceError
from app.sync.service import poll_user, select_folder

router = APIRouter(prefix="/api")


_DRIVE_ID = re.compile(r"[A-Za-z0-9_-]+")


def is_valid_drive_id(value: str) -> bool:
    """Drive ids are URL-safe base64-ish; anything else never reaches a Drive URL."""
    return bool(_DRIVE_ID.fullmatch(value))


class FolderChoice(BaseModel):
    folder_id: str


@router.get("/folders")
def search_folders(q: str = "", source: DocumentSource = Depends(user_source)) -> list[dict]:
    return [{"id": f.id, "name": f.name} for f in source.search_folders(q)]


@router.put("/folder")
def put_folder(
    body: FolderChoice,
    user: User = Depends(current_user),
    source: DocumentSource = Depends(user_source),
    session: Session = Depends(get_session),
) -> dict:
    if not is_valid_drive_id(body.folder_id):
        raise HTTPException(status_code=400, detail="invalid folder id")
    try:
        watched = select_folder(session, user, source, body.folder_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="that id is not a folder") from None
    except SourceError as err:
        if err.status != 404:
            raise
        raise HTTPException(
            status_code=400, detail="folder not found, or not shared with this Google account"
        ) from None
    session.commit()
    return folder_status(session, user, watched)


@router.get("/folder")
def get_folder(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    watched = session.scalar(select(WatchedFolder).where(WatchedFolder.user_id == user.id))
    if watched is None:
        raise HTTPException(status_code=404, detail="no folder chosen")
    return folder_status(session, user, watched)


@router.post("/folder/sync")
def sync_now(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
    settings: Settings = Depends(auth_settings),
) -> dict:
    if session.scalar(select(WatchedFolder.id).where(WatchedFolder.user_id == user.id)) is None:
        raise HTTPException(status_code=404, detail="no folder chosen")
    result = poll_user(session, user, lambda s, u: drive_source_for(s, u, settings))
    return {"queued": result.queued, "ignored": result.ignored}


def folder_status(session: Session, user: User, watched: WatchedFolder) -> dict:
    counts = dict(
        session.execute(
            select(SourceFile.status, func.count())
            .where(SourceFile.user_id == user.id)
            .group_by(SourceFile.status)
        ).all()
    )
    return {
        "name": watched.name,
        "last_synced_at": watched.last_synced_at,
        "last_error": watched.last_error,
        "counts_by_status": counts,
        "needs_reconnect": user.needs_reconnect,
    }
