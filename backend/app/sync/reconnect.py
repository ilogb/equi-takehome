"""Re-queue files that failed only because the user's Google grant had lapsed.

Testing-mode grants expire after 7 days (spike §C.1); without this, every file processed
while the account was disconnected would need a manual Retry after signing in again.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.jobs.queue import enqueue
from app.models import FileStatus, SourceFile, User
from app.sources.base import RECONNECT_MARKER


def failed_by_reconnect(status: str, error: str | None) -> bool:
    return status == FileStatus.failed.value and bool(error) and RECONNECT_MARKER in error


def requeue_after_reconnect(session: Session, user: User) -> int:
    """Queue again this user's files that failed with ReconnectRequired. Returns how many."""
    failed = session.scalars(
        select(SourceFile).where(SourceFile.user_id == user.id, SourceFile.status == FileStatus.failed.value)
    ).all()
    count = 0
    for file in failed:
        if failed_by_reconnect(file.status, file.error) and enqueue(session, file.id) is not None:
            file.error = None
            count += 1
    return count
