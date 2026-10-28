from app.config import Settings


def test_settings_allowed_emails_parsed(monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", " A@x.com, b@y.com ")
    assert Settings(_env_file=None).allowed_emails == ["a@x.com", "b@y.com"]


def test_settings_allowed_emails_empty(monkeypatch):
    monkeypatch.setenv("ALLOWED_EMAILS", "")
    assert Settings(_env_file=None).allowed_emails == []


def test_settings_defaults(monkeypatch):
    for k in ("PUBLIC_BASE_URL", "FRONTEND_URL", "WORKER_CONCURRENCY", "POLL_SECONDS"):
        monkeypatch.delenv(k, raising=False)
    s = Settings(_env_file=None)
    assert s.public_base_url == "http://localhost:8000"
    assert s.frontend_url == "http://localhost:5173"
    assert s.worker_concurrency == 3
    assert s.poll_seconds == 60
