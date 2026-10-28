"""Postgres-backed job queue: claim with FOR UPDATE SKIP LOCKED, leases, retry/backoff."""

from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models import FileStatus, Job, JobStatus, SourceFile

# Longer than one LLM call (600 s timeout, no SDK retries) plus persistence.
LEASE = timedelta(minutes=45)
BACKOFFS = (timedelta(seconds=30), timedelta(seconds=120), timedelta(seconds=600))


MAX_ATTEMPTS = len(BACKOFFS) + 1
LOST_MESSAGE = "worker lost the job too many times"


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


def reclaim_exhausted(status: str, attempts: int) -> bool:
    """True if an expired-lease job has used up its attempts and must fail, not rerun."""
    return status == JobStatus.running.value and attempts >= MAX_ATTEMPTS


def enqueue(session: Session, file_id: int, force: bool = False) -> Job | None:
    """Queue a file; None if an unfinished job already exists (unless `force`)."""
    # Lock the file row so concurrent enqueues (poller, "Sync now") serialise.
    file = session.scalar(select(SourceFile).where(SourceFile.id == file_id).with_for_update())
    if file is None:
        raise ValueError(f"source file {file_id} not found")
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
    job = Job(user_id=file.user_id, source_file_id=file_id, force=force)
    session.add(job)
    file.status = FileStatus.queued.value
    session.flush()
    return job


def claim(session: Session, now: datetime, lease: timedelta = LEASE) -> Job | None:
    """Take one runnable job: queued and due, or running with an expired lease.

    Expired-lease jobs that already used all their attempts are failed instead of run.
    """
    while True:
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
        file = session.get(SourceFile, job.source_file_id)
        if reclaim_exhausted(job.status, job.attempts):
            job.status = JobStatus.failed.value
            job.last_error = LOST_MESSAGE
            job.lease_until = None
            if file is not None:
                file.status = FileStatus.failed.value
                file.error = LOST_MESSAGE
            session.flush()
            continue
        job.status = JobStatus.running.value
        job.lease_until = now + lease
        job.attempts += 1
        if file is not None:
            file.status = FileStatus.processing.value
        session.flush()
        return job


def _holds_lease(session: Session, job: Job, lease: datetime | None) -> bool:
    """Re-read the job under lock; True if this worker's lease is still the current one."""
    if lease is None:
        return True
    session.refresh(job, with_for_update=True)
    return job.status == JobStatus.running.value and job.lease_until == lease


def complete(session: Session, job: Job, lease: datetime | None = None) -> bool:
    """Mark done. With `lease` (value set at claim), does nothing if the lease was lost."""
    if not _holds_lease(session, job, lease):
        return False
    job.status = JobStatus.done.value
    job.lease_until = None
    job.last_error = None
    session.flush()
    return True


def fail(
    session: Session, job: Job, err: BaseException, now: datetime, lease: datetime | None = None
) -> bool:
    """Record a failed attempt. With `lease`, does nothing if the lease was lost."""
    if not _holds_lease(session, job, lease):
        return False
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
    return True
