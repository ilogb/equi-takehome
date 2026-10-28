import secrets

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.api import auth as auth_api
from app.api import folder as folder_api
from app.auth.crypto import AuthConfigError
from app.config import Settings, get_settings
from app.sources.base import ReconnectRequired, SourceError


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Document Intelligence")
    app.state.settings = settings

    # Signed, HttpOnly, SameSite=Lax cookie. Without SESSION_SECRET a throwaway key is used
    # so the app still starts; every auth route then refuses with AuthConfigError.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret or secrets.token_urlsafe(32),
        session_cookie="session",
        same_site="lax",
        https_only=settings.public_base_url.startswith("https://"),
    )

    @app.exception_handler(AuthConfigError)
    def _auth_config(request: Request, exc: AuthConfigError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=500)

    @app.exception_handler(ReconnectRequired)
    def _reconnect(request: Request, exc: ReconnectRequired) -> JSONResponse:
        return JSONResponse({"detail": "reconnect_required"}, status_code=409)

    @app.exception_handler(SourceError)
    def _source(request: Request, exc: SourceError) -> JSONResponse:
        return JSONResponse({"detail": str(exc), "retryable": exc.retryable}, status_code=502)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_api.router)
    app.include_router(folder_api.router)
    return app


app = create_app()
