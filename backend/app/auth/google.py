"""Google OAuth web flow (spike §C): one consent for openid/email/profile + drive.readonly,
offline access, and credentials rebuilt from the stored refresh token."""

import os
from collections.abc import Callable
from dataclasses import dataclass

from google.auth.exceptions import RefreshError, TransportError
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from sqlalchemy.orm import Session

from app.auth.crypto import decrypt, require_auth_config
from app.config import Settings
from app.models import User
from app.sources.base import ReconnectRequired, SourceError
from app.sources.drive import GoogleDriveSource, is_invalid_grant

# Google answers "email" as ".../userinfo.email" and may reorder scopes; without this
# oauthlib rejects the token response as a scope change.
os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/drive.readonly",
]
AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URI = "https://oauth2.googleapis.com/token"
USERINFO_URI = "https://openidconnect.googleapis.com/v1/userinfo"
CALLBACK_PATH = "/api/auth/google/callback"


@dataclass(frozen=True)
class GoogleIdentity:
    email: str
    name: str | None
    email_verified: bool
    refresh_token: str | None


# (code, pkce code_verifier) -> identity; swapped out in tests.
IdentityExchange = Callable[[str, str | None], GoogleIdentity]


def redirect_uri(settings: Settings) -> str:
    return settings.public_base_url.rstrip("/") + CALLBACK_PATH


def _flow(settings: Settings, code_verifier: str | None = None) -> Flow:
    require_auth_config(settings)
    config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": AUTH_URI,
            "token_uri": TOKEN_URI,
            "redirect_uris": [redirect_uri(settings)],
        }
    }
    return Flow.from_client_config(
        config, scopes=SCOPES, redirect_uri=redirect_uri(settings), code_verifier=code_verifier
    )


def authorization_url(settings: Settings, state: str) -> tuple[str, str | None]:
    """(URL to send the browser to, PKCE code verifier to keep until the callback)."""
    flow = _flow(settings)
    # prompt=consent makes Google return a refresh token on every sign-in.
    url, _ = flow.authorization_url(access_type="offline", prompt="consent", state=state)
    return url, flow.code_verifier


def exchange_code(settings: Settings) -> IdentityExchange:
    def exchange(code: str, code_verifier: str | None) -> GoogleIdentity:
        flow = _flow(settings, code_verifier)
        flow.fetch_token(code=code)
        creds = flow.credentials
        resp = AuthorizedSession(creds).get(USERINFO_URI, timeout=30)
        resp.raise_for_status()
        info = resp.json()
        return GoogleIdentity(
            email=(info.get("email") or "").strip().lower(),
            name=info.get("name"),
            email_verified=bool(info.get("email_verified")),
            refresh_token=creds.refresh_token,
        )

    return exchange


def is_allowed(email: str, allowed: list[str]) -> bool:
    email = email.strip().lower()
    return bool(email) and email in {a.strip().lower() for a in allowed}


def _default_refresh(creds: Credentials) -> None:
    creds.refresh(Request())


def mark_needs_reconnect(session: Session, user: User) -> None:
    """Set the flag and commit at once, so a caller's later rollback cannot undo it."""
    user.needs_reconnect = True
    session.commit()


def credentials_for(
    session: Session,
    user: User,
    settings: Settings,
    refresh: Callable[[Credentials], None] = _default_refresh,
) -> Credentials:
    """Fresh credentials from the stored refresh token.

    Only `invalid_grant` (revoked, expired, Testing-mode 7-day limit) sets `needs_reconnect`
    and raises ReconnectRequired; other refresh failures are retryable SourceErrors.
    """
    if not user.refresh_token_enc:
        mark_needs_reconnect(session, user)
        raise ReconnectRequired("no Google refresh token stored; reconnect required")
    creds = Credentials(
        token=None,
        refresh_token=decrypt(settings, user.refresh_token_enc),
        token_uri=TOKEN_URI,
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=SCOPES,
    )
    try:
        refresh(creds)
    except RefreshError as err:
        if is_invalid_grant(err):
            mark_needs_reconnect(session, user)
            raise ReconnectRequired() from None
        raise SourceError("Google token refresh failed", retryable=True, status=401) from None
    except TransportError:
        raise SourceError("Google token endpoint unreachable", retryable=True) from None
    return creds


def drive_source_for(session: Session, user: User, settings: Settings) -> GoogleDriveSource:
    return GoogleDriveSource(credentials_for(session, user, settings))
