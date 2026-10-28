# Deferred integration tests

Written after the user has tried the app (plan: "Testing approach", Q38). Builders append each deferred test here under its task number: test name and assertions.

## Task 1

- `conftest.pg_url` (fixture, session-scoped): starts a `pgvector/pgvector:pg16` testcontainer and yields its SQLAlchemy URL (`postgresql+psycopg://...`).
- `conftest.session` (fixture): a SQLAlchemy `Session` bound to `pg_url` with the schema created; rolled back/cleaned after each test.
- `conftest.client` (fixture): a FastAPI `TestClient` over `create_app(Settings(database_url=pg_url))` with `get_session` overridden to the `session` fixture.
- `tests/integration/test_health.py::test_health_ok_against_db`: with the db-backed `client`, `GET /api/health` returns 200 and `{"status": "ok"}` (the unit version already covers the no-DB case).
- `tests/integration/test_db.py::test_session_roundtrip`: `session.execute(text("select 1"))` works against the container and `CREATE EXTENSION vector` succeeds.

## Task 2

- `tests/integration/test_schema.py::test_migration_creates_tables`: after `alembic upgrade head` against the container, all 10 application tables exist (user, watched_folder, source_file, document, fund, fund_alias, printed_table, common_row, chunk, job). Note: the plan says "11 tables"; the brief lists 10 distinct tables.
- `tests/integration/test_schema.py::test_vector_column_is_1536`: inserting a `chunk` with a 1536-length embedding succeeds; a 1535-length one raises a database error.
- `tests/integration/test_schema.py::test_unique_drive_file_per_user`: the same `drive_file_id` for two different users is allowed; inserting it twice for one user raises `IntegrityError`.

- (controller, from Task 2 review) `test_migration_matches_models`: after `alembic upgrade head`, `alembic check` reports no differences (hand-written migration vs ORM metadata).

## Task 7

- `tests/integration/test_funds.py::test_resolve_reuses_alias`: `resolve_fund(session, uid, "Northwind Global Macro Fund, L.P.", None)` then `resolve_fund(session, uid, "Northwind Global Macro Fund LP", None)` return the same `Fund` (same id); exactly one `Fund` row and one `FundAlias` row exist for the user (both spellings share the normalized key `northwind global macro`). Also: a differently-named variant that normalizes differently (e.g. adding "II") creates a second fund with its own alias.
- `tests/integration/test_funds.py::test_funds_are_per_user`: `resolve_fund` with the same name for two different users returns two different `Fund` rows (different ids, each with its own `user_id`); `known_fund_names(session, uid)` returns only that user's canonical names.
