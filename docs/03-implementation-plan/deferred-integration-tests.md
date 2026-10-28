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
- `tests/integration/test_funds.py::test_resolve_race_returns_existing`: with an alias/fund for `(user, key)` committed by a second session after the first session's lookup misses (simulate by patching `_lookup_fund` to return None once, or two threads), `resolve_fund` catches the `IntegrityError` from the savepoint, re-reads the alias and returns the existing `Fund`; exactly one `Fund` and one `FundAlias` row exist and the outer session remains usable.
- `tests/integration/test_funds.py::test_resolve_empty_key_names_stay_distinct`: `resolve_fund` for "The Fund" and "LP" yields two different funds.

## Task 8

All need Postgres (`tests/integration/test_store.py`, FakeLLM, recorded extractions). The pure logic (`build_rows`, `find_conflicts`, `chunk_texts`) is unit-tested in `tests/unit/test_store.py`.

- `test_persist_man_ahl`: `persist_extraction` of the Man AHL extraction: the 2026 Jan return `common_row` has `value == Decimal("0.0842")` and `period_end == 2026-01-31`; `printed_table` count == 18.
- `test_fundsmith_dates_snapped`: the Jan return row has `period_end == 2026-01-31` and `value == Decimal("-0.005")`.
- `test_harborline_account_rows_only`: 4 rows, all `entity_kind == "account"`, `fund_id IS NULL` (no fund created); no row with `value` in `{0.217, 0.124}`.
- `test_reextract_replaces`: persisting twice for one file leaves one `document` and the same row, table and chunk counts (old children deleted).
- `test_conflict_marked`: two documents for one user, same fund, class, measure and month, values `0.0237` vs `0.0235`: `mark_conflicts` returns 2 and both rows have `conflict=True`; `0.02370` vs `0.02373`: returns 0, neither flagged; a rerun clears stale flags.
- `test_share_classes_not_conflicts`: Alderbank A (`0.0312`) and I (`0.0321`) for Jan: no conflict.
- `test_needs_review_outlier`: a monthly return `"62%"` gives `needs_review=True`, `review_reason == "monthly return beyond ±50%"`, and the file status is `needs_review` (otherwise `done`).
- `test_chunks_embedded`: every chunk has a 1536-length embedding and a non-empty `tsv`; embedding is batched in groups of 64.
