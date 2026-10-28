"""Google sign-in routes."""

import hmac
import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.crypto import encrypt
from app.auth.deps import auth_settings, current_user, get_identity_exchange
from app.auth.google import IdentityExchange, authorization_url, is_allowed
from app.config import Settings
from app.db import get_session
from app.models import User, WatchedFolder

log = logging.getLogger("auth")
router = APIRouter(prefix="/api/auth")


def _front(settings: Settings, path: str) -> RedirectResponse:
    return RedirectResponse(settings.frontend_url.rstrip("/") + path, status_code=302)


def _has_folder(session: Session, user_id: int) -> bool:
    return session.scalar(select(WatchedFolder.id).where(WatchedFolder.user_id == user_id)) is not None


@router.get("/google/start")
def google_start(request: Request, settings: Settings = Depends(auth_settings)) -> RedirectResponse:
    state = secrets.token_urlsafe(32)
    url, verifier = authorization_url(settings, state)
    request.session["oauth_state"] = state
    request.session["oauth_verifier"] = verifier
    return RedirectResponse(url, status_code=302)


@router.get("/google/callback")
def google_callback(
    request: Request,
    state: str = "",
    code: str = "",
    error: str = "",
    settings: Settings = Depends(auth_settings),
    exchange: IdentityExchange = Depends(get_identity_exchange),
    session: Session = Depends(get_session),
) -> RedirectResponse:
    expected = request.session.pop("oauth_state", None)
    verifier = request.session.pop("oauth_verifier", None)
    if not expected or not state or not hmac.compare_digest(expected.encode(), state.encode()):
        raise HTTPException(status_code=400, detail="invalid OAuth state")
    if error or not code:
        return _front(settings, "/connect?error=access_denied")

    try:
        identity = exchange(code, verifier)
    except Exception as err:  # never log the code or token response, only the failure type
        log.warning("Google code exchange failed: %s", type(err).__name__)
        return _front(settings, "/connect?error=auth_failed")
    if not identity.email_verified or not is_allowed(identity.email, settings.allowed_emails):
        request.session.clear()
        return _front(settings, "/connect?error=not_allowed")

    email = identity.email.strip().lower()
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, needs_reconnect=False)
        session.add(user)
    if identity.refresh_token:
        user.refresh_token_enc = encrypt(settings, identity.refresh_token)
        user.needs_reconnect = False
    elif user.refresh_token_enc is None:
        user.needs_reconnect = True
    session.commit()

    request.session.clear()
    request.session["uid"] = user.id
    request.session["name"] = identity.name
    return _front(settings, "/library" if _has_folder(session, user.id) else "/connect")


@router.get("/me")
def me(request: Request, user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    return {
        "email": user.email,
        "name": request.session.get("name"),
        "needs_reconnect": user.needs_reconnect,
        "has_folder": _has_folder(session, user.id),
    }


@router.post("/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}
