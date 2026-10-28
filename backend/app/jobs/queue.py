"""Postgres-backed job queue: claim with FOR UPDATE SKIP LOCKED, leases, retry/backoff."""

from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import FileStatus, Job, JobStatus, SourceFile

LEASE = timedelta(minutes=15)
BACKOFFS = (timedelta(seconds=30), timedelta(seconds=120), timedelta(seconds=600))


class PermanentError(Exception):
    """A failure no retry can fix (e.g. no credentials configured)."""

    retryable = False


def backoff(attempts: int) -> timedelta | None:
    """Delay before the next try after `attempts` tries have been made; None = give up."""
    if 1 <= attempts <= len(BACKOFFS):
        return BACKOFFS[attempts - 1]
    return None


def next_state(job_attempts: int, err: BaseException) -> tuple[str, timedelta | None, str]:
    """(job status, run_after delta, error text) after a failed attempt.

    Errors without a `retryable` flag (unexpected exceptions) are treated as retryable.
    """
    text = str(err) or type(err).__name__
    if getattr(err, "retryable", True):
        delay = backoff(job_attempts)
        if delay is not None:
            return JobStatus.queued.value, delay, text
    return JobStatus.failed.value, None, text


def is_claimable(status: str, run_after: datetime, lease_until: datetime | None, now: datetime) -> bool:
    """Python mirror of the SQL predicate used by `claim`."""
    if status == JobStatus.queued.value:
        return run_after <= now
    if status == JobStatus.running.value:
        return lease_until is not None and lease_until < now
    return False


def enqueue(session: Session, file_id: int, force: bool = False) -> Job | None:
    """Queue a file; None if an unfinished job already exists (unless `force`)."""
    if not force:
        unfinished = session.scalar(
            select(Job.id)
            .where(
                Job.source_file_id == file_id,
                Job.status.in_([JobStatus.queued.value, JobStatus.running.value]),
            )
            .limit(1)
        )
        if unfinished is not None:
            return None
    file = session.get(SourceFile, file_id)
    if file is None:
        raise ValueError(f"source file {file_id} not found")
    job = Job(user_id=file.user_id, source_file_id=file_id, force=force)
    session.add(job)
    file.status = FileStatus.queued.value
    session.flush()
    return job


def claim(session: Session, now: datetime, lease: timedelta = LEASE) -> Job | None:
    """Take one runnable job: queued and due, or running with an expired lease."""
    job = session.scalar(
        select(Job)
        .where(
            or_(
                and_(Job.status == JobStatus.queued.value, Job.run_after <= now),
                and_(Job.status == JobStatus.running.value, Job.lease_until < now),
            )
        )
        .order_by(Job.run_after, Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    job.status = JobStatus.running.value
    job.lease_until = now + lease
    job.attempts += 1
    file = session.get(SourceFile, job.source_file_id)
    if file is not None:
        file.status = FileStatus.processing.value
    session.flush()
    return job


def complete(session: Session, job: Job) -> None:
    job.status = JobStatus.done.value
    job.lease_until = None
    job.last_error = None
    session.flush()


def fail(session: Session, job: Job, err: BaseException, now: datetime) -> None:
    status, delay, text = next_state(job.attempts, err)
    job.status = status
    job.last_error = text
    job.lease_until = None
    file = session.get(SourceFile, job.source_file_id)
    if delay is not None:
        job.run_after = now + delay
        if file is not None:
            file.status = FileStatus.queued.value
    elif file is not None:
        file.status = FileStatus.failed.value
        file.error = text
    session.flush()
