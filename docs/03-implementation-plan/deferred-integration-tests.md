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

## Task 9

All need Postgres (`tests/integration/test_run.py`, `FakeDriveSource`, `FakeLLM`). Routing, head/tail slicing, tabular extraction and NUL stripping are unit-tested in `tests/unit/test_run.py`.

- `test_pdf_done`: `process_file` on the Man AHL PDF returns `done` (or `needs_review`) and one `document` with rows exists.
- `test_scanned_no_llm_call`: the image-only PDF returns `scanned_no_text`; the LLM saw zero `extract`/`map_table`/`embed` calls; a `document` row holds the page text and has no chunks.
- `test_png_unsupported`: mime `image/png` returns `unsupported`, `error` mentions the type, no document.
- `test_eml_extracted`: Kestrel `.eml` yields a `return` `common_row` with value `0.019`.
- `test_csv_mapped`: Alderbank CSV yields 29 `common_row`s; one `printed_table` holding the raw cells.
- `test_document_with_no_rows_is_done_and_searchable`: an extraction with zero tables and rows gives status `done` and chunks exist (search asserted in Task 13).
- `test_corrupt_pdf_failed`: garbage bytes as a PDF give `failed` with a readable `error` and no exception.
- `test_conflicts_marked_after_persist`: after two files with differing values for one identity are processed, `common_row.conflict` is true on both (`mark_conflicts` called).
- `test_llm_error_propagates`: an `LLMError` from the LLM escapes `process_file` and leaves the file status unchanged.
- `test_nul_text_persists`: a document whose text contained NUL persists without a Postgres error.

## Task 10

All need Postgres (`tests/integration/test_queue.py`, injected `now`). Backoff schedule, `next_state` (retryable vs non-retryable) and the claim predicate are unit-tested in `tests/unit/test_jobs.py`.

- `test_enqueue_dedupes`: `enqueue(file_id)` twice returns a `Job` then `None` (one job row); with `force=True` a second job is created; after the first job is `done`, `enqueue` returns a new job. The file status is `queued`.
- `test_claim_skip_locked`: with two queued jobs, two sessions that each `claim` before committing get different jobs; a third claim returns `None`. Claimed jobs are `running`, `lease_until == now + 15 min`, `attempts == 1`, and the file is `processing`.
- `test_backoff_then_failed`: a retryable `LLMError` via `fail` after each claim sets `run_after` to now +30 s, +120 s, +600 s with job `queued` and file `queued`; the fourth failure sets job and file `failed` with `last_error`/`error` text. A job with `run_after` in the future is not claimed.
- `test_non_retryable_fails_immediately`: `fail` with `LLMError(retryable=False)` (and `PermanentError`) on attempt 1 sets job `failed` and file `failed` with the error text.
- `test_expired_lease_is_reclaimed`: a `running` job with `lease_until` in the past is claimed again (attempts incremented); one with `lease_until` in the future is not.
- `test_process_one_marks_done`: with `FakeDriveSource`/`FakeLLM`, `process_one` on a queued job leaves the job `done`; with `source_for` raising `PermanentError`, job and file end `failed` and the worker returns `True`.
- `test_enqueue_race`: two sessions call `enqueue(file_id)` concurrently (second blocks on the `source_file` row lock until the first commits); exactly one returns a `Job`, the other `None`, and one unfinished job row exists.
- `test_exhausted_lease_fails`: a `running` job with expired lease and `attempts == 4` is not returned by `claim`; it becomes `failed` with `last_error == "worker lost the job too many times"` and its file is `failed`; the next runnable job (if any) is claimed in the same call.
- `test_fenced_complete_and_fail`: after worker A claims and its lease expires, worker B reclaims; `complete(job, lease=A's lease)` / `fail(..., lease=A's lease)` return `False` and leave B's job state unchanged.
- `test_missing_file_fails_permanently`: a job whose `source_file` row is gone ends `failed` after one attempt via `process_one`.

## Task 11

All need Postgres (`tests/integration/test_auth.py`, `tests/integration/test_sync.py`, `FakeDriveSource` from `tests/fakes.py`). Unit-tested without a DB: crypto round-trip and fail-fast config (`tests/unit/test_auth.py`), allowlist, `credentials_for` invalid_grant handling with a fake session, the OAuth callback (bad state 400, unlisted/unverified email redirect with nothing stored, encrypted token on sign-in, cookie flags) with the token exchange and DB overridden; Drive error classification, retries, paging and the changes mask over a fake HTTP session (`tests/unit/test_drive.py`); `decide_change`, `walk_folder`, `snapshot_folder` call order, `apply_changes` and `sync_step` (incl. 410) over `FakeDriveSource` (`tests/unit/test_sync.py`).

- `test_callback_rejects_unlisted_email`: against a real DB, an unlisted email leaves zero `user` rows; redirect `…/connect?error=not_allowed`.
- `test_refresh_token_encrypted_at_rest`: after a successful callback, the `user.refresh_token_enc` column read with raw SQL does not contain the plaintext; `decrypt` returns it. A second sign-in with no refresh token keeps the stored one.
- `test_invalid_grant_sets_needs_reconnect`: `credentials_for` with a refresh raising `invalid_grant` raises `ReconnectRequired`, and after the caller's `rollback()` the `user.needs_reconnect` column is still `true` (committed inside).
- `test_token_saved_before_listing`: `select_folder` stores `watched_folder.page_token` equal to the token returned before the first `list_children` call.
- `test_initial_sync_includes_subfolders`: after `select_folder` on the fake tree, `source_file` rows exist for files in `docs/real` and `docs/synthetic` with `path` `docs/real/…` / `docs/synthetic/…`, each supported one has a queued `job`; a PNG row has status `unsupported` and no job; `descendant_ids` holds every subfolder id (not the root).
- `test_poll_picks_up_file_in_new_subfolder`: folder-created change then file change in it → one new `source_file` (path `…/<new folder>/<file>`), one job, `descendant_ids` includes the new folder; `SyncResult.queued == 1`.
- `test_poll_ignores_other_folders`: a change parented outside the tree creates no row.
- `test_poll_ignores_edits_and_deletes`: edited, trashed and removed known files create no job and do not change the existing rows.
- `test_410_rewalks`: with the saved token expired, `poll_changes` saves a fresh token, queues only files without a row, and sets `last_synced_at`.
- `test_poll_saves_response_token_and_last_synced_at`: after a poll, `page_token` equals the token from the response and `last_synced_at` is set; `last_error` cleared.
- `test_poll_user_records_error`: a `SourceError` from the source rolls back partial rows, sets `watched_folder.last_error`, commits, and re-raises; a `ReconnectRequired` also sets `needs_reconnect`.
- `test_poll_all_skips_needs_reconnect`: two users with folders, one `needs_reconnect=true`: only the other user's source is built; one user's failure does not stop the other.
- `test_change_folder_deletes_files`: `select_folder` to a different folder id deletes that user's `source_file` rows (and by cascade documents, rows, chunks, jobs) and that user's `fund_alias` and `fund` rows, and not another user's.
- `test_concurrent_poll_serialised`: two sessions polling one user: the second blocks on the `watched_folder` row lock and then sees the advanced token (no duplicate rows).
- `test_folder_routes`: `GET /api/folder` returns `{name, last_synced_at, last_error, counts_by_status, needs_reconnect}`; 404 before a folder is chosen; `/api/auth/me` `has_folder` true after `PUT /api/folder`; all routes 401 without a session.
- `test_worker_source_for_marks_reconnect`: `process_one` with the Drive `source_for` and a revoked token fails the job at once (`failed`, attempt 1) and `user.needs_reconnect` is true.
- `test_requeue_after_reconnect`: a user with `needs_reconnect=true` and files `failed` with `error` containing "reconnect required" (plus one failed with a Drive 404 error) signs in again with a new refresh token: the reconnect-failed files get a new queued `job`, status `queued`, `error` NULL; the 404 one stays `failed`; `needs_reconnect` is false; another user's failed files are untouched.
- `test_poll_folder_moved_out`: after a watched subfolder is moved out (change with parents outside the set), `watched_folder.descendant_ids` no longer holds it or its subfolders; a later new file in it creates no row; existing rows under it remain.
