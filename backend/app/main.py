import secrets

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.analyze.tools import build_tools
from app.api import analyze as analyze_api
from app.api import auth as auth_api
from app.api import dashboard as dashboard_api
from app.api import documents as documents_api
from app.api import files as files_api
from app.api import folder as folder_api
from app.api import funds as funds_api
from app.api import meta as meta_api
from app.api import rows as rows_api
from app.api import search as search_api
from app.auth.crypto import AuthConfigError
from app.config import Settings, get_settings
from app.sources.base import ReconnectRequired, SourceError


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Document Intelligence")
    app.state.settings = settings
    # Per-process secret for Analyze's in-process tool calls; never logged or returned.
    app.state.internal_token = secrets.token_urlsafe(32)

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
    for module in (files_api, documents_api, rows_api, funds_api, meta_api, search_api, analyze_api, dashboard_api):
        app.include_router(module.router)
    build_tools(app)  # fails startup if an `analyze` GET route lacks an operation id or docstring
    return app


app = create_app()
