"""Secrets for sign-in: Fernet encryption of refresh tokens and the auth config check.

Checked when auth is used, not at import, so the app (and `/api/health`) start without them.
"""

from cryptography.fernet import Fernet, InvalidToken

from app.config import Settings


class AuthConfigError(RuntimeError):
    """Sign-in is used but a required setting is empty."""


def require_auth_config(settings: Settings) -> None:
    missing = [
        name
        for name, value in (
            ("SESSION_SECRET", settings.session_secret),
            ("FERNET_KEY", settings.fernet_key),
            ("GOOGLE_CLIENT_ID", settings.google_client_id),
            ("GOOGLE_CLIENT_SECRET", settings.google_client_secret),
        )
        if not value
    ]
    if missing:
        raise AuthConfigError(f"Google sign-in needs {', '.join(missing)} set (see `make keys` and .env.example)")


def _fernet(settings: Settings) -> Fernet:
    if not settings.fernet_key:
        raise AuthConfigError("FERNET_KEY is not set (generate one with `make keys`)")
    try:
        return Fernet(settings.fernet_key.encode())
    except ValueError:
        raise AuthConfigError("FERNET_KEY is not a valid Fernet key (generate one with `make keys`)") from None


def encrypt(settings: Settings, plaintext: str) -> str:
    return _fernet(settings).encrypt(plaintext.encode()).decode()


def decrypt(settings: Settings, token: str) -> str:
    try:
        return _fernet(settings).decrypt(token.encode()).decode()
    except InvalidToken:
        raise AuthConfigError("stored token cannot be decrypted with the current FERNET_KEY") from None
