# Deferred integration tests

Written after the user has tried the app (plan: "Testing approach", Q38). Builders append each deferred test here under its task number: test name and assertions.

## Task 1

- `conftest.pg_url` (fixture, session-scoped): starts a `pgvector/pgvector:pg16` testcontainer and yields its SQLAlchemy URL (`postgresql+psycopg://...`).
- `conftest.session` (fixture): a SQLAlchemy `Session` bound to `pg_url` with the schema created; rolled back/cleaned after each test.
- `conftest.client` (fixture): a FastAPI `TestClient` over `create_app(Settings(database_url=pg_url))` with `get_session` overridden to the `session` fixture.
- `tests/integration/test_health.py::test_health_ok_against_db`: with the db-backed `client`, `GET /api/health` returns 200 and `{"status": "ok"}` (the unit version already covers the no-DB case).
- `tests/integration/test_db.py::test_session_roundtrip`: `session.execute(text("select 1"))` works against the container and `CREATE EXTENSION vector` succeeds.
