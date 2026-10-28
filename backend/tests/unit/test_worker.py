"""process_one over fake sessions and a stubbed queue (no database)."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.jobs import worker

LEASE = datetime(2026, 10, 28, tzinfo=UTC)


class FakeSession:
    def __init__(self):
        self.calls: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def commit(self):
        self.calls.append("commit")

    def rollback(self):
        self.calls.append("rollback")

    def get(self, model, id):
        return SimpleNamespace(id=id, source_file_id=5, lease_until=LEASE)


@pytest.fixture
def session(monkeypatch):
    s = FakeSession()
    job = SimpleNamespace(id=1, source_file_id=5, lease_until=LEASE)
    monkeypatch.setattr(worker, "claim", lambda sess, now: job)
    return s


def run(session):
    return worker.process_one(lambda: session, settings=None, llm=None, source_for=lambda s, f: None)


def test_completed_job_commits(session, monkeypatch):
    monkeypatch.setattr(worker, "process_file", lambda *a: session.calls.append("process"))
    monkeypatch.setattr(worker, "complete", lambda *a: True)
    assert run(session)
    assert session.calls == ["commit", "process", "commit"]


def test_lost_lease_on_complete_rolls_back_pipeline_writes(session, monkeypatch):
    monkeypatch.setattr(worker, "process_file", lambda *a: session.calls.append("process"))
    monkeypatch.setattr(worker, "complete", lambda *a: False)
    assert run(session)
    assert session.calls == ["commit", "process", "rollback"]


def test_lost_lease_on_fail_rolls_back(session, monkeypatch):
    def boom(*a):
        raise RuntimeError("x")

    monkeypatch.setattr(worker, "process_file", boom)
    monkeypatch.setattr(worker, "fail", lambda *a: False)
    assert run(session)
    assert session.calls == ["commit", "rollback", "rollback"]


def test_failure_recorded_commits(session, monkeypatch):
    def boom(*a):
        raise RuntimeError("x")

    monkeypatch.setattr(worker, "process_file", boom)
    monkeypatch.setattr(worker, "fail", lambda *a: True)
    assert run(session)
    assert session.calls == ["commit", "rollback", "commit"]
