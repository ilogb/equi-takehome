from datetime import datetime, timedelta, timezone

from app.jobs.queue import MAX_ATTEMPTS, PermanentError, backoff, is_claimable, next_state, reclaim_exhausted
from app.llm.base import IncompleteResponse, LLMError

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc)


def test_backoff_schedule():
    assert backoff(1) == timedelta(seconds=30)
    assert backoff(2) == timedelta(seconds=120)
    assert backoff(3) == timedelta(seconds=600)
    assert backoff(4) is None


def test_retryable_backs_off_then_fails():
    err = LLMError("rate limited", retryable=True)
    assert next_state(1, err) == ("queued", timedelta(seconds=30), "rate limited")
    assert next_state(2, err)[:2] == ("queued", timedelta(seconds=120))
    assert next_state(3, err)[:2] == ("queued", timedelta(seconds=600))
    assert next_state(4, err) == ("failed", None, "rate limited")


def test_incomplete_response_is_retryable():
    assert next_state(1, IncompleteResponse())[0] == "queued"


def test_non_retryable_fails_immediately():
    err = LLMError("bad request", retryable=False)
    assert next_state(1, err) == ("failed", None, "bad request")
    assert next_state(1, PermanentError("no source"))[0] == "failed"


def test_unexpected_exception_is_retryable():
    assert next_state(1, RuntimeError("db gone"))[:2] == ("queued", timedelta(seconds=30))


def test_error_text_falls_back_to_class_name():
    assert next_state(1, RuntimeError())[2] == "RuntimeError"


def test_claim_predicate():
    past, future = NOW - timedelta(seconds=1), NOW + timedelta(seconds=1)
    assert is_claimable("queued", NOW, None, NOW)
    assert not is_claimable("queued", future, None, NOW)
    assert is_claimable("running", NOW, past, NOW)  # expired lease
    assert not is_claimable("running", NOW, future, NOW)
    assert not is_claimable("running", NOW, NOW, NOW)  # lease_until < now is strict
    assert not is_claimable("done", past, past, NOW)
    assert not is_claimable("failed", past, past, NOW)


def test_reclaim_cap():
    assert MAX_ATTEMPTS == 4
    assert not reclaim_exhausted("running", 3)
    assert reclaim_exhausted("running", 4)
    assert reclaim_exhausted("running", 9)
    assert not reclaim_exhausted("queued", 9)
