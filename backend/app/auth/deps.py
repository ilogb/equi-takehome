"""FastAPI dependencies for sign-in and per-user Drive access."""

import hmac

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.crypto import require_auth_config
from app.auth.google import IdentityExchange, drive_source_for, exchange_code
from app.config import Settings
from app.db import get_session
from app.models import User
from app.sources.base import DocumentSource

# Analyze's in-process tool calls run as the asking user with these two headers. The token is a
# per-process random secret (app.state.internal_token) that never leaves the process.
INTERNAL_USER_HEADER = "X-Internal-User"
INTERNAL_TOKEN_HEADER = "X-Internal-Token"


def app_settings(request: Request) -> Settings:
    return request.app.state.settings


def auth_settings(settings: Settings = Depends(app_settings)) -> Settings:
    """Settings, after checking the secrets sign-in needs (AuthConfigError -> 500 with the reason)."""
    require_auth_config(settings)
    return settings


def get_identity_exchange(settings: Settings = Depends(auth_settings)) -> IdentityExchange:
    return exchange_code(settings)


def current_user(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(auth_settings),
) -> User:
    if INTERNAL_USER_HEADER in request.headers or INTERNAL_TOKEN_HEADER in request.headers:
        uid = _internal_uid(request)
    else:
        uid = request.session.get("uid")
    user = session.get(User, uid) if isinstance(uid, int) else None
    if user is None:
        raise HTTPException(status_code=401, detail="not signed in")
    return user


def user_source(
    user: User = Depends(current_user),
    session: Session = Depends(get_session),
    settings: Settings = Depends(auth_settings),
) -> DocumentSource:
    return drive_source_for(session, user, settings)


def _internal_uid(request: Request) -> int | None:
    """The user id from an in-process Analyze call, or None (-> 401) unless the token matches.

    A request carrying either internal header is judged only by them, never by its cookie,
    so a forged header cannot fall back to, or ride on, someone's session.
    """
    expected = getattr(request.app.state, "internal_token", None)
    token = request.headers.get(INTERNAL_TOKEN_HEADER, "")
    raw = request.headers.get(INTERNAL_USER_HEADER, "")
    if not expected or not hmac.compare_digest(token.encode(), expected.encode()):
        return None
    return int(raw) if raw.isascii() and raw.isdigit() else None
