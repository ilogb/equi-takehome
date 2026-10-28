"""FastAPI dependencies for sign-in and per-user Drive access."""

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.auth.crypto import require_auth_config
from app.auth.google import IdentityExchange, drive_source_for, exchange_code
from app.config import Settings
from app.db import get_session
from app.models import User
from app.sources.base import DocumentSource


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
