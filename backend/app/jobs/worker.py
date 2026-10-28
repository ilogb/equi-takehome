"""Worker loop: `python -m app.jobs.worker`."""

import logging
import signal
import threading
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.jobs.queue import PermanentError, claim, complete, fail
from app.llm.base import LLMProvider
from app.models import Job, SourceFile, User
from app.pipeline.run import process_file
from app.sources.base import DocumentSource

log = logging.getLogger("worker")

PollFn = Callable[[Session], None]
SourceFor = Callable[[Session, SourceFile], DocumentSource]
IDLE_SECONDS = 2.0


def _now() -> datetime:
    return datetime.now(UTC)


def process_one(
    session_factory: Callable[[], Session],
    settings: Settings,
    llm: LLMProvider,
    source_for: SourceFor,
) -> bool:
    """Claim and run one job in its own session. Returns False if nothing was runnable."""
    with session_factory() as session:
        job = claim(session, _now())
        session.commit()
        if job is None:
            return False
        job_id, lease = job.id, job.lease_until
        try:
            file = session.get(SourceFile, job.source_file_id)
            if file is None:
                raise PermanentError(f"source file {job.source_file_id} no longer exists")
            process_file(session, file, source_for(session, file), llm, settings)
            if not complete(session, job, lease):
                log.warning("job %s lease lost before completion; ignoring result", job_id)
            session.commit()
        except Exception as err:
            if getattr(err, "retryable", None) is not False:
                log.exception("job %s failed", job_id)
            else:
                log.warning("job %s failed permanently: %s", job_id, err)
            session.rollback()
            job = session.get(Job, job_id)
            if job is None or not fail(session, job, err, _now(), lease):
                log.warning("job %s lease lost before failure was recorded; ignoring", job_id)
            session.commit()
        return True


def _worker_loop(stop: threading.Event, run_once: Callable[[], bool]) -> None:
    while not stop.is_set():
        try:
            busy = run_once()
        except Exception:
            log.exception("worker iteration crashed")
            busy = False
        if not busy:
            stop.wait(IDLE_SECONDS)


def _poll_loop(stop: threading.Event, interval: float, poll_fn: PollFn, session_factory) -> None:
    while not stop.is_set():
        try:
            with session_factory() as session:
                poll_fn(session)
                session.commit()
        except Exception:
            log.exception("poll failed")
        stop.wait(interval)


def run_worker(
    settings: Settings,
    poll_fn: PollFn | None = None,
    source_for: SourceFor | None = None,
) -> None:
    from app.db import SessionLocal
    from app.llm.openai_provider import OpenAIProvider

    llm = OpenAIProvider(settings)
    source_for = source_for or _no_source
    stop = threading.Event()

    def run_once() -> bool:
        return process_one(SessionLocal, settings, llm, source_for)

    threads = [
        threading.Thread(target=_worker_loop, args=(stop, run_once), name=f"worker-{i}", daemon=True)
        for i in range(settings.worker_concurrency)
    ]
    if poll_fn is not None:
        threads.append(
            threading.Thread(
                target=_poll_loop,
                args=(stop, settings.poll_seconds, poll_fn, SessionLocal),
                name="poller",
                daemon=True,
            )
        )
    for t in threads:
        t.start()
    log.info("worker started: %d threads", len(threads))
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        while not stop.wait(1.0):
            pass
    except KeyboardInterrupt:
        log.info("stopping")
    finally:
        log.info("shutting down")
        stop.set()
        for t in threads:
            t.join(timeout=5)


def _no_source(session: Session, file: SourceFile) -> DocumentSource:
    raise PermanentError("Drive source not configured")


def drive_source_for_file(settings: Settings) -> SourceFor:
    """Build the Drive source from the file owner's stored Google credentials.

    A revoked grant raises ReconnectRequired (not retryable), so the job fails at once and
    the user is flagged `needs_reconnect` (committed inside credentials_for).
    """
    from app.auth.google import drive_source_for

    def source_for(session: Session, file: SourceFile) -> DocumentSource:
        user = session.get(User, file.user_id)
        if user is None:
            raise PermanentError(f"user {file.user_id} no longer exists")
        return drive_source_for(session, user, settings)

    return source_for


def drive_poll_fn(settings: Settings) -> PollFn:
    """Poll Drive for every user with a folder, skipping users who must reconnect."""
    from app.auth.google import drive_source_for
    from app.sync.service import poll_all

    def poll(session: Session) -> None:
        poll_all(session, lambda s, user: drive_source_for(s, user, settings))

    return poll


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    _settings = get_settings()
    run_worker(_settings, poll_fn=drive_poll_fn(_settings), source_for=drive_source_for_file(_settings))
