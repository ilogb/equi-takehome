"""Google sign-in: crypto, allowlist, invalid_grant handling and the OAuth callback (no DB, no network)."""

from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from google.auth.exceptions import RefreshError

from app.api import auth as auth_api
from app.api.folder import is_valid_drive_id
from app.auth.crypto import AuthConfigError, decrypt, encrypt, require_auth_config
from app.auth.deps import current_user, get_identity_exchange, user_source
from app.auth.google import GoogleIdentity, credentials_for, is_allowed
from app.config import Settings
from app.db import get_session
from app.main import create_app
from app.models import User
from app.sources.base import ReconnectRequired, SourceError
from app.sync.reconnect import failed_by_reconnect
from tests.fakes import FakeDriveSource
from tests.fakes import file as rfile
from tests.fakes import folder as rfolder

FERNET = Fernet.generate_key().decode()


def settings(**kw) -> Settings:
    base = dict(
        _env_file=None,
        database_url="postgresql+psycopg://x/x",
        google_client_id="cid.apps.googleusercontent.com",
        google_client_secret="csecret",
        allowed_emails="allowed@example.com",
        session_secret="s" * 48,
        fernet_key=FERNET,
    )
    base.update(kw)
    return Settings(**base)


# --- crypto --------------------------------------------------------------------------


def test_refresh_token_encrypted_at_rest():
    s = settings()
    enc = encrypt(s, "1//refresh-plaintext")
    assert "refresh-plaintext" not in enc
    assert decrypt(s, enc) == "1//refresh-plaintext"


def test_missing_secrets_fail_fast_with_clear_error():
    with pytest.raises(AuthConfigError, match="FERNET_KEY"):
        encrypt(settings(fernet_key=""), "x")
    with pytest.raises(AuthConfigError, match="SESSION_SECRET"):
        require_auth_config(settings(session_secret=""))
    with pytest.raises(AuthConfigError, match="GOOGLE_CLIENT_ID"):
        require_auth_config(settings(google_client_id=""))


def test_app_imports_without_secrets():
    create_app(settings(session_secret="", fernet_key=""))  # no error until auth is used


# --- allowlist -----------------------------------------------------------------------


def test_allowlist_case_insensitive():
    allowed = ["allowed@example.com"]
    assert is_allowed("Allowed@Example.COM", allowed)
    assert is_allowed(" allowed@example.com ", allowed)
    assert not is_allowed("other@example.com", allowed)
    assert not is_allowed("", allowed)
    assert not is_allowed("allowed@example.com", [])


# --- credentials_for -------------------------------------------------------------------


class FakeSession:
    """Just enough of a SQLAlchemy Session for the auth code paths."""

    def __init__(self, existing_user: User | None = None):
        self.existing_user = existing_user
        self.added: list = []
        self.commits = 0

    def scalar(self, stmt):
        text = str(stmt)
        if "FROM \"user\"" in text or "FROM user" in text:
            return self.existing_user
        return None

    def get(self, model, pk):
        if model is User and self.existing_user is not None and self.existing_user.id == pk:
            return self.existing_user
        return None

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        for i, obj in enumerate(self.added, start=1):
            if getattr(obj, "id", None) is None:
                obj.id = i

    def commit(self):
        self.flush()
        self.commits += 1


def _user(s: Settings) -> User:
    return User(id=7, email="allowed@example.com", refresh_token_enc=encrypt(s, "rt"), needs_reconnect=False)


def test_invalid_grant_sets_needs_reconnect():
    s, db = settings(), FakeSession()
    user = _user(s)

    def refresh(creds):
        raise RefreshError("invalid_grant: Token has been expired or revoked.", {"error": "invalid_grant"})

    with pytest.raises(ReconnectRequired) as err:
        credentials_for(db, user, s, refresh=refresh)
    assert err.value.retryable is False
    assert user.needs_reconnect is True
    assert db.commits == 1  # persisted at once so a caller's rollback cannot undo it


def test_other_refresh_error_is_retryable_and_keeps_account():
    s, db = settings(), FakeSession()
    user = _user(s)

    def refresh(creds):
        raise RefreshError("temporarily_unavailable", {"error": "temporarily_unavailable"}, retryable=True)

    with pytest.raises(SourceError) as err:
        credentials_for(db, user, s, refresh=refresh)
    assert not isinstance(err.value, ReconnectRequired)
    assert err.value.retryable is True
    assert user.needs_reconnect is False


def test_credentials_built_from_decrypted_token():
    s, db = settings(), FakeSession()
    seen = {}
    creds = credentials_for(db, _user(s), s, refresh=lambda c: seen.setdefault("rt", c.refresh_token))
    assert seen["rt"] == "rt"
    assert creds.client_id == s.google_client_id


def test_user_without_token_needs_reconnect():
    s, db = settings(), FakeSession()
    user = User(id=7, email="a@example.com", refresh_token_enc=None, needs_reconnect=False)
    with pytest.raises(ReconnectRequired):
        credentials_for(db, user, s, refresh=lambda c: None)
    assert user.needs_reconnect is True


# --- OAuth routes ------------------------------------------------------------------------


def client_for(db: FakeSession, identity: GoogleIdentity, s: Settings | None = None) -> TestClient:
    app = create_app(s or settings())
    app.dependency_overrides[get_session] = lambda: db
    app.dependency_overrides[get_identity_exchange] = lambda: (lambda code, verifier: identity)
    return TestClient(app, follow_redirects=False)


def start(client: TestClient) -> str:
    resp = client.get("/api/auth/google/start")
    assert resp.status_code in (302, 307)
    q = parse_qs(urlparse(resp.headers["location"]).query)
    assert q["access_type"] == ["offline"]
    assert q["prompt"] == ["select_account consent"]
    scopes = q["scope"][0].split()
    assert "openid" in scopes and "https://www.googleapis.com/auth/drive.readonly" in scopes
    assert q["redirect_uri"] == ["http://localhost:8000/api/auth/google/callback"]
    return q["state"][0]


def test_session_cookie_httponly_lax():
    client = client_for(FakeSession(), GoogleIdentity("allowed@example.com", "A", True, "rt"))
    resp = client.get("/api/auth/google/start")
    cookie = resp.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie


def test_callback_bad_state_400():
    db = FakeSession()
    client = client_for(db, GoogleIdentity("allowed@example.com", "A", True, "rt"))
    start(client)
    resp = client.get("/api/auth/google/callback", params={"state": "forged", "code": "c"})
    assert resp.status_code == 400
    assert db.added == []


def test_callback_without_started_flow_400():
    db = FakeSession()
    client = client_for(db, GoogleIdentity("allowed@example.com", "A", True, "rt"))
    resp = client.get("/api/auth/google/callback", params={"state": "x", "code": "c"})
    assert resp.status_code == 400


def test_callback_rejects_unlisted_email():
    db = FakeSession()
    client = client_for(db, GoogleIdentity("intruder@example.com", "I", True, "rt"))
    state = start(client)
    resp = client.get("/api/auth/google/callback", params={"state": state, "code": "c"})
    assert resp.status_code in (302, 307)
    assert resp.headers["location"] == "http://localhost:5173/connect?error=not_allowed"
    assert db.added == [] and db.commits == 0
    assert client.get("/api/auth/me").status_code == 401


def test_callback_rejects_unverified_email():
    db = FakeSession()
    client = client_for(db, GoogleIdentity("allowed@example.com", "A", False, "rt"))
    state = start(client)
    resp = client.get("/api/auth/google/callback", params={"state": state, "code": "c"})
    assert resp.headers["location"].endswith("/connect?error=not_allowed")
    assert db.added == []


def test_callback_stores_encrypted_token_and_signs_in():
    s = settings()
    db = FakeSession()
    client = client_for(db, GoogleIdentity("Allowed@Example.com", "Al", True, "1//plain-refresh"), s)
    state = start(client)
    resp = client.get("/api/auth/google/callback", params={"state": state, "code": "c"})
    assert resp.headers["location"] == "http://localhost:5173/connect"  # no folder yet
    (user,) = db.added
    assert user.email == "allowed@example.com"
    assert "plain-refresh" not in user.refresh_token_enc
    assert decrypt(s, user.refresh_token_enc) == "1//plain-refresh"
    db.existing_user = user
    me = client.get("/api/auth/me").json()
    assert me == {"email": "allowed@example.com", "name": "Al", "needs_reconnect": False, "has_folder": False}
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_callback_keeps_existing_token_when_none_returned():
    s = settings()
    existing = User(id=3, email="allowed@example.com", refresh_token_enc=encrypt(s, "old"), needs_reconnect=True)
    db = FakeSession(existing_user=existing)
    client = client_for(db, GoogleIdentity("allowed@example.com", "A", True, None), s)
    state = start(client)
    client.get("/api/auth/google/callback", params={"state": state, "code": "c"})
    assert decrypt(s, existing.refresh_token_enc) == "old"
    assert existing.needs_reconnect is True  # no new token, so still disconnected


def test_auth_routes_fail_clearly_without_secrets():
    client = client_for(FakeSession(), GoogleIdentity("a@b.c", "A", True, "rt"), settings(session_secret=""))
    resp = client.get("/api/auth/google/start")
    assert resp.status_code == 500
    assert "SESSION_SECRET" in resp.json()["detail"]


# --- reconnect requeue, folder id validation, PUT /api/folder errors --------------------



def test_failed_by_reconnect_selection():
    assert failed_by_reconnect("failed", "Google access was revoked or expired; reconnect required")
    assert failed_by_reconnect("failed", "no Google refresh token stored; reconnect required")
    assert not failed_by_reconnect("failed", "Drive HTTP 404: File not found")
    assert not failed_by_reconnect("failed", None)
    assert not failed_by_reconnect("done", "reconnect required")


def test_reconnect_message_is_what_selection_matches():
    assert failed_by_reconnect("failed", str(ReconnectRequired()))


def test_callback_requeues_after_reconnect(monkeypatch):
    s = settings()
    existing = User(id=3, email="allowed@example.com", refresh_token_enc=encrypt(s, "old"), needs_reconnect=True)
    db = FakeSession(existing_user=existing)
    calls = []
    monkeypatch.setattr(auth_api, "requeue_after_reconnect", lambda session, user: calls.append(user.id) or 0)
    client = client_for(db, GoogleIdentity("allowed@example.com", "A", True, "new"), s)
    state = start(client)
    client.get("/api/auth/google/callback", params={"state": state, "code": "c"})
    assert calls == [3]
    assert existing.needs_reconnect is False


def test_drive_id_validation():
    assert is_valid_drive_id("1vMG2qvqZ5h74hzdyOstiUwGpslMobKhc")
    assert is_valid_drive_id("a_b-C")
    for bad in ["", "../x", "a/b", "a?alt=media", "a b", "a'b", "a%2F"]:
        assert not is_valid_drive_id(bad)


def folder_client(src: FakeDriveSource) -> TestClient:
    app = create_app(settings())
    user = User(id=1, email="allowed@example.com", needs_reconnect=False)
    app.dependency_overrides[get_session] = lambda: FakeSession(existing_user=user)
    app.dependency_overrides[current_user] = lambda: user
    app.dependency_overrides[user_source] = lambda: src
    return TestClient(app)


def test_put_folder_rejects_bad_id():
    src = FakeDriveSource(items=[rfolder("root", "R")])
    resp = folder_client(src).put("/api/folder", json={"folder_id": "../files?alt=media"})
    assert resp.status_code == 400
    assert src.calls == []  # never reached Drive


def test_put_folder_not_found_is_400():
    resp = folder_client(FakeDriveSource()).put("/api/folder", json={"folder_id": "missing123"})
    assert resp.status_code == 400
    assert "not found" in resp.json()["detail"].lower()


def test_put_folder_on_a_file_is_400():
    src = FakeDriveSource(items=[rfolder("root", "R"), rfile("f1", "a.pdf", "root")])
    resp = folder_client(src).put("/api/folder", json={"folder_id": "f1"})
    assert resp.status_code == 400
    assert "not a folder" in resp.json()["detail"].lower()
