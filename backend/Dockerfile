# Build context is the repo root (compose and CapRover both use it).
FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv
RUN groupadd --system app && useradd --system --gid app --home-dir /app app
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ .
RUN chown -R app:app /app
ENV PATH="/app/.venv/bin:$PATH" FORWARDED_ALLOW_IPS=127.0.0.1
USER app
EXPOSE 8000
# One image, two roles. API by default; set APP_ROLE=worker for the worker app.
CMD ["sh", "-c", "if [ \"$APP_ROLE\" = worker ]; then exec python -m app.jobs.worker; fi; alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips \"$FORWARDED_ALLOW_IPS\""]
