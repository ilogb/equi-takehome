# Document Intelligence Web App Implementation Plan (v0, Claude-only)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Provenance:** blind pass, written by Claude with no input from the user. See `docs/README.md`.

**Goal:** A local web app that syncs a Google Drive folder, extracts structured fund-performance data from PDFs, HTML/emails and CSVs with Claude, and lets the user browse, filter, search and ask questions with cited sources.

**Architecture:** FastAPI + SQLAlchemy over SQLite (WAL, FTS5). An in-process worker thread drains a DB-backed `job` table, and an APScheduler job polls the Drive Changes API every 60 s. Extraction runs through an `Extractor` protocol (Claude in production, a fake in tests), followed by deterministic checks: value re-parse, quote check, fund resolution. A React/Vite SPA talks to the JSON API.

**Tech Stack:** Python 3.12, uv, FastAPI, SQLAlchemy 2.0, pydantic v2, pandas, pdfplumber, beautifulsoup4, google-api-python-client, google-auth-oauthlib, cryptography (Fernet), APScheduler 3.x, anthropic SDK, pytest; React 18 + TypeScript + Vite, TanStack Query/Table, Tailwind, react-pdf, Vitest.

**Spec:** `docs/00-only-claude-ai/2026-10-27-document-intelligence-design.md`

## Global Constraints

- Returns are stored as fractions: `0.0123` means 1.23%. Displayed as percent with two decimals.
- Monetary values and returns are `Decimal` in Python and `Numeric(20, 10)` in SQL; never float.
- Extraction model `claude-sonnet-5-5`; Q&A model `claude-sonnet-5-5`; `PROMPT_VERSION = "extract-v1"`, `CSV_PROMPT_VERSION = "csvmap-v1"`.
- Drive scope `https://www.googleapis.com/auth/drive.readonly` plus `openid`, `email`.
- Sync poll interval 60 s. Retry backoff 30 s, 120 s, 600 s, then `failed`.
- PDFs over 50 pages → `unsupported`. Top-level folder only.
- Quote length 10–200 characters. Monthly return outside ±0.5 → `needs_review`. Conflict tolerance `0.00005`.
- Q&A: at most 6 tool calls; SQL time limit 2 s; row cap 200; read-only connection.
- Server binds `127.0.0.1`. No test touches the network.
- Python package root `backend/app`; tests `backend/tests`; frontend `frontend/`.

## Review Focus

1. **Percent written several ways in one document** (`1.2%`, `(1.2)`, `−1.2`, `12 bps`, `0.012` in a CSV whose header says `%`): every one is stored as the right fraction. → tests in Task 2 and Task 6.
2. **A file edited in Drive while its earlier revision is still processing, or edited twice quickly**: only the latest revision ends up `is_current`, with no duplicate observations. → test in Task 8.
3. **A file moved out of the folder rather than deleted** (the change shows the file with `parents` no longer including the folder): its data disappears from tables and Q&A. → test in Task 10.
4. **The same fund named differently across managers' documents** (`Alpha Fund, L.P.` vs `ALPHA FUND LP`): one fund row. → test in Task 7.
5. **A question the model tries to answer with a write or a join outside the views** (`DELETE`, `ATTACH`, `sqlite_master`, `PRAGMA`): refused by the guard, and the agent reports it couldn't answer. → test in Task 12.

---

## File Structure

```
Makefile                      dev, test, eval, fmt
.env.example
README.md
backend/
  pyproject.toml
  app/
    main.py                   FastAPI app factory, lifespan starts worker + scheduler
    config.py                 Settings (pydantic-settings)
    db.py                     engine, SessionLocal, init_db() incl. FTS + views
    models.py                 ORM tables (spec §5)
    parsing/values.py         parse_value(), parse_period_end()
    parsing/text.py           load_document_text() per file kind
    extraction/schema.py      pydantic DocumentExtraction, CsvMapping
    extraction/extractor.py   Extractor protocol, ClaudeExtractor, FakeExtractor
    extraction/csv_apply.py   apply_csv_mapping()
    extraction/persist.py     persist_extraction(): checks, fund resolution, conflicts
    funds.py                  normalize_fund_key(), resolve_fund(), merge_funds()
    jobs.py                   enqueue(), claim_next(), worker loop, process_job()
    google/oauth.py           flow, token store (Fernet)
    google/drive.py           DriveClient protocol, GoogleDriveClient, download/export
    google/sync.py            initial_sync(), poll_changes()
    ask/sql_guard.py          ReadOnlyQuery runner
    ask/agent.py              answer_question()
    api/*.py                  routers: auth, folder, files, documents, observations, funds, ask
  tests/ ...                  mirrors app/
evals/
  generate_corpus.py          builds synthetic docs + truth JSON
  corpus/                     generated output (committed)
  run_eval.py
frontend/
  src/api.ts, src/routes/{Connect,Library,DocumentDetail,Performance,Ask,Funds}.tsx
  src/components/{StatusChip,PercentCell,SourceLink,AppShell}.tsx
```

---

### Task 1: Backend skeleton, settings, database and models

**Files:**
- Create: `Makefile`, `.env.example`, `backend/pyproject.toml`, `backend/app/{main,config,db,models}.py`
- Test: `backend/tests/test_db.py`

**Interfaces:**
- Produces: `Settings` (`database_url`, `anthropic_api_key`, `google_client_id`, `google_client_secret`, `fernet_key`, `frontend_origin`, `start_background: bool`); `init_db(engine)`; `SessionLocal`; ORM classes `GoogleAccount, WatchedFolder, SourceFile, Document, Fund, FundAlias, Observation, Fact, Job` with columns from spec §5; enums `FileStatus, DocType, Metric, PeriodKind, Unit, JobStatus` as `StrEnum`; `create_app(settings) -> FastAPI` with `GET /api/health`.

- [ ] **Step 1: Write failing tests**
  - `test_init_db_creates_tables_fts_and_views`: after `init_db`, `sqlite_master` contains every table, `document_fts`, `v_performance`, `v_facts`, `v_documents`.
  - `test_wal_mode`: `PRAGMA journal_mode` returns `wal`.
  - `test_v_performance_excludes_non_current_and_deleted`: insert one current + one non-current document with an observation each, plus one under a `deleted` source_file; the view returns exactly 1 row.
  - `test_health`: `GET /api/health` → `200 {"status": "ok"}` with `start_background=False`.
- [ ] **Step 2: Run** `cd backend && uv run pytest tests/test_db.py -v` → FAIL (import errors).
- [ ] **Step 3: Implement.** `init_db` runs `Base.metadata.create_all`, then raw DDL for FTS5 (`document_fts(document_id UNINDEXED, page UNINDEXED, file_name, text)`) and the three views. Enable WAL and `foreign_keys=ON` in a `connect` event listener. Makefile targets: `dev` (uvicorn on 127.0.0.1:8000 + `npm --prefix frontend run dev`), `test`, `eval`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(backend): skeleton, settings, schema and views`

### Task 2: Value and date parsing

**Files:** Create `backend/app/parsing/values.py`; Test `backend/tests/parsing/test_values.py`

**Interfaces:**
- Produces: `parse_value(text: str, unit_hint: Unit | None = None) -> ParsedValue | None` where `ParsedValue(value: Decimal, unit: Unit, currency: str | None)`; `month_end(year: int, month: int) -> date`; `parse_period_end(text: str, period_kind: PeriodKind) -> date | None`.

- [ ] **Step 1: Write failing tests** (parametrised `test_parse_value`):
  `"1.23%"→0.0123 fraction`, `"(1.2)%"→-0.012`, `"−0.8%"` (U+2212) `→-0.008`, `"-0.8 %"→-0.008`, `"12 bps"→0.0012`, `"1,234.5"` with hint `number`→`1234.5`, `"$1.2bn"→1200000000 currency USD`, `"€350m"→350000000 EUR`, `"n/a"→None`, `"—"→None`, `"0.012"` with hint `fraction`→`0.012`, `"1.2"` with hint `percent-as-number`→`0.012`.
  `test_parse_period_end`: `("Jan 2026", month)→2026-01-31`, `("2024-02", month)→2024-02-29`, `("31/03/2026", qtd)→2026-03-31`, `("March 2026", ytd)→2026-03-31`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** with regexes and `Decimal`. `Unit` gains no new member; `percent-as-number` is a `unit_hint` string literal used only by the CSV path. Dates via `dateutil.parser` with `dayfirst` guessed from a day value over 12; a missing day means month end.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(parsing): value and period parsing`

### Task 3: Text loading per file kind

**Files:** Create `backend/app/parsing/text.py`; Test `backend/tests/parsing/test_text.py`; fixtures `backend/tests/fixtures/{two_page.pdf,email.eml,report.html,wide.csv}` (tiny, generated in the test module's conftest with reportlab and the stdlib `email` package)

**Interfaces:**
- Produces: `FileKind = Literal["pdf","html","csv"]`; `kind_for_mime(mime: str, name: str) -> FileKind | None`; `LoadedText(kind: FileKind, pages: list[str], page_count: int)`; `load_document_text(data: bytes, kind: FileKind) -> LoadedText`; `TooManyPagesError`.

- [ ] **Step 1: Write failing tests:**
  - `test_kind_for_mime`: `application/pdf→pdf`, `application/vnd.google-apps.document→pdf`, `text/html→html`, `message/rfc822→html`, `application/vnd.google-apps.spreadsheet→csv`, `text/csv→csv`, `("application/octet-stream","x.csv")→csv`, `image/png→None`.
  - `test_pdf_pages`: `two_page.pdf` → 2 pages, page 2 contains `"February"`.
  - `test_eml_prefers_html_part_and_strips_script`: the result contains the table cell text, not the `<script>` body.
  - `test_html_tables_keep_rows`: a `<tr><td>Jan</td><td>1.2%</td></tr>` row comes out as one line `Jan | 1.2%`.
  - `test_pdf_over_50_pages_raises`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement** with pdfplumber (`page.extract_text() or ""`) and BeautifulSoup (drop script/style; flatten tables to `|`-joined lines). CSV returns one page holding the raw text.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(parsing): text loading for pdf, html, eml, csv`

### Task 4: Extraction schema and Extractor protocol

**Files:** Create `backend/app/extraction/{schema,extractor}.py`, `backend/app/extraction/prompts/{extract_v1,csvmap_v1}.md`; Test `backend/tests/extraction/test_extractor.py`

**Interfaces:**
- Produces (pydantic):
  - `ObservationOut(metric: Metric, period_kind: PeriodKind, period_end: date, value: Decimal, unit: Unit, currency: str | None, value_as_written: str, benchmark_name: str | None, page: int, quote: constr(min_length=10, max_length=200))`
  - `FactOut(key: str, value_text: str, quote: str)`
  - `FundOut(name: str, share_class: str | None, facts: list[FactOut], observations: list[ObservationOut])`
  - `DocumentExtraction(doc_type: DocType, manager: str | None, as_of_date: date | None, currency: str | None, summary: str, funds: list[FundOut])`
  - `CsvMapping(layout: Literal["long","wide"], fund_column: str | None, constant_fund: str | None, manager_column: str | None, constant_manager: str | None, date_column: str | None, metric_column: str | None, constant_metric: Metric | None, value_column: str | None, period_columns: list[str], period_kind: PeriodKind, unit_hint: Literal["percent","fraction","percent-as-number","currency","number"], date_format: str | None, benchmark_column: str | None)`
  - `class Extractor(Protocol): def extract_document(self, *, kind: FileKind, data: bytes, text: LoadedText, known_funds: list[str]) -> DocumentExtraction; def map_csv(self, *, header: list[str], sample_rows: list[list[str]], known_funds: list[str]) -> CsvMapping`
  - `ClaudeExtractor(client: anthropic.Anthropic, model: str)`; `FakeExtractor(document: DocumentExtraction | None, mapping: CsvMapping | None)`; `ExtractionError`.

- [ ] **Step 1: Write failing tests** (Anthropic client replaced with a stub object that records the request):
  - `test_pdf_request_uses_document_block_and_forced_tool`: the request has one `document` block with base64 PDF, `tool_choice={"type":"tool","name":"record_extraction"}`, and `input_schema == DocumentExtraction.model_json_schema()`.
  - `test_html_request_wraps_text_as_data`: user content contains `<document>` … `</document>` tags around the text, and the known-fund list.
  - `test_invalid_tool_output_gets_one_repair_retry`: the stub returns invalid JSON, then valid; the result is valid and the second request includes the validation error text.
  - `test_two_invalid_outputs_raise_extraction_error`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Prompts hold the rules in spec §6.2 bullet "The prompt", with the system prompt version-tagged. `max_tokens=16000`.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(extraction): schema, Claude extractor with forced tool output`

### Task 5: Fund resolution and merge

**Files:** Create `backend/app/funds.py`; Test `backend/tests/test_funds.py`

**Interfaces:**
- Produces: `normalize_fund_key(name: str) -> str`; `resolve_fund(session, name: str, manager: str | None) -> Fund`; `merge_funds(session, keep_id: int, merge_id: int) -> Fund`; `known_fund_names(session) -> list[str]`.

- [ ] **Step 1: Write failing tests:**
  - `test_normalize`: `"Alpha Fund, L.P."`, `"ALPHA FUND LP"`, `"Alpha  Fund"` → `"alpha"`; `"Smith & Co Global Ltd"` → `"smith and co global"`.
  - `test_resolve_reuses_by_alias`: resolving two spellings yields one `Fund` and two `FundAlias` rows.
  - `test_merge_moves_observations_and_aliases`: after merge, every observation points to `keep_id`, `merge_id` is gone, and resolving the merged name returns `keep_id`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(funds): normalisation, resolution, merge`

### Task 6: Apply a CSV mapping

**Files:** Create `backend/app/extraction/csv_apply.py`; Test `backend/tests/extraction/test_csv_apply.py`

**Interfaces:**
- Consumes: `CsvMapping`, `parse_value`, `parse_period_end`.
- Produces: `apply_csv_mapping(csv_text: str, mapping: CsvMapping, file_name: str) -> DocumentExtraction`. Each `ObservationOut.page = 1`, `quote = f"row {n}, {column}: {raw}"`, which is padded to the 10-character minimum by its prefix.

- [ ] **Step 1: Write failing tests:**
  - `test_long_layout`: columns `Fund,Date,Return` with `"1.2%"` → 3 observations, values `0.012`, period ends at month end.
  - `test_wide_layout`: columns `Fund,Jan-26,Feb-26` → 2 observations per fund row.
  - `test_percent_as_number_header`: header `Return (%)`, value `1.2`, `unit_hint="percent-as-number"` → `0.012`.
  - `test_blank_and_na_cells_skipped`.
  - `test_constant_fund_single_fund_file`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** with `pandas.read_csv(dtype=str, keep_default_na=False)` and `melt` for wide layouts. **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(extraction): deterministic CSV mapping application`

### Task 7: Persist an extraction with checks and conflicts

**Files:** Create `backend/app/extraction/persist.py`; Test `backend/tests/extraction/test_persist.py`

**Interfaces:**
- Consumes: `DocumentExtraction`, `LoadedText`, `resolve_fund`, `parse_value`.
- Produces: `persist_extraction(session, source_file: SourceFile, content_hash: str, text: LoadedText, extraction: DocumentExtraction, model: str, prompt_version: str) -> Document` — inserts the document (`is_current=True`, flips earlier revisions to `False`), observations, facts and FTS rows; sets `source_file.status` to `done` or `needs_review`. `verify_quote(quote: str, pages: list[str], page: int) -> bool | None` (`None` when the page has no text). `find_conflicts(session, observation_ids: list[int] | None = None) -> list[Conflict]` with `Conflict(fund_id, metric, period_kind, period_end, observation_ids: list[int])`.

- [ ] **Step 1: Write failing tests:**
  - `test_parser_overrides_model_value`: model `value=1.2`, `value_as_written="1.2%"` → stored `0.012`, `needs_review=True`.
  - `test_quote_verified_whitespace_insensitive` / `test_quote_not_found_marks_unverified` / `test_empty_page_text_gives_none`.
  - `test_monthly_return_over_50pct_needs_review`.
  - `test_period_after_as_of_needs_review`.
  - `test_new_revision_replaces_current`: persist twice for one file → one `is_current` document; `v_performance` row count equals the second extraction's.
  - `test_conflict_detected_across_documents`: two files, same fund/month, `0.0120` vs `0.0135` → one `Conflict`; `0.01200` vs `0.01203` → none.
  - `test_name_variants_one_fund` (Review Focus 4): two extractions naming `"Alpha Fund, L.P."` and `"ALPHA FUND LP"` → one `Fund`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(extraction): persistence, verification, conflicts`

### Task 8: Job queue and worker

**Files:** Create `backend/app/jobs.py`; Test `backend/tests/test_jobs.py`

**Interfaces:**
- Consumes: `load_document_text`, `Extractor`, `apply_csv_mapping`, `persist_extraction`, `known_fund_names`.
- Produces: `Downloader = Callable[[SourceFile], bytes]` (Task 9's `GoogleDriveClient.download` satisfies it); `enqueue(session, source_file_id: int, content_hash: str, force: bool = False) -> Job | None` (`None` when that hash is already queued, processing or done, unless `force`); `claim_next(session, now: datetime) -> Job | None` (atomic `UPDATE … WHERE status='queued' AND run_after<=now … RETURNING`); `process_job(session, job, download: Downloader, extractor, now) -> None`; `Worker(session_factory, downloader_factory: Callable[[], Downloader], extractor, poll_seconds=1.0)` with `start()`/`stop()`.

- [ ] **Step 1: Write failing tests** (FakeDrive, FakeExtractor, injected `now`):
  - `test_enqueue_is_idempotent_per_hash`; `test_force_enqueues_again`.
  - `test_success_path_sets_done`.
  - `test_transient_error_backoff`: an extractor that raises `anthropic.APIConnectionError` → attempt 1 `run_after=now+30s`, then 120 s, 600 s, then `failed` with `last_error` set on both job and file.
  - `test_unsupported_mime_marks_unsupported_without_llm_call`.
  - `test_too_many_pages_unsupported_with_reason`.
  - `test_stale_revision_does_not_become_current` (Review Focus 2): enqueue hash A, then hash B; process B first, then A → the current document has hash B.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Before persisting, `process_job` skips (marks the job `done`, no document) when `job.content_hash != source_file.content_hash`. Worker exceptions are logged and never kill the thread.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(jobs): DB-backed queue, retries, worker thread`

### Task 9: Google OAuth and Drive client

**Files:** Create `backend/app/google/{oauth,drive}.py`, `backend/app/api/auth.py`; Test `backend/tests/google/test_oauth.py`, `test_drive.py`

**Interfaces:**
- Produces: `build_flow(settings, state: str | None) -> Flow`; `TokenStore(session, fernet)` with `save(creds)`, `load() -> Credentials | None` (refreshes and re-saves; raises `ReconnectRequired` on `RefreshError`); routes `GET /api/auth/google/start` → 302 to Google, `GET /api/auth/google/callback` → stores the token and 302s to `{frontend_origin}/connect`, `GET /api/auth/status` → `{connected, email, needs_reconnect}`, `POST /api/auth/disconnect`.
  `class DriveClient(Protocol)`: `search_folders(query: str) -> list[DriveFolder]`, `list_folder(folder_id) -> list[DriveFile]`, `start_page_token() -> str`, `list_changes(token) -> tuple[list[DriveChange], str]`, `download(file: SourceFile) -> bytes`. `DriveFile(id, name, mime_type, content_hash, modified_time, parents: list[str], trashed: bool)`; `DriveChange(file_id, removed: bool, file: DriveFile | None)`. `GoogleDriveClient(creds)` and `FakeDriveClient` (in `tests/fakes.py`). `InvalidPageToken` for HTTP 410.

- [ ] **Step 1: Write failing tests:**
  - `test_token_roundtrip_encrypted`: the stored column doesn't contain the refresh token in plain text, and `load()` returns equal creds.
  - `test_refresh_error_raises_reconnect`.
  - `test_callback_rejects_bad_state` → 400.
  - `test_download_exports_native_files`: with a mocked `service`, a Google Doc calls `files().export(mimeType="application/pdf")`, a Sheet calls `export(mimeType="text/csv")`, and a PDF calls `get_media`.
  - `test_content_hash_falls_back_to_version` for native files.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (state kept in a signed cookie). **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(google): OAuth flow, encrypted token store, Drive client`

### Task 10: Folder selection and sync

**Files:** Create `backend/app/google/sync.py`, `backend/app/api/folder.py`; Test `backend/tests/google/test_sync.py`

**Interfaces:**
- Consumes: `DriveClient`, `enqueue`.
- Produces: `select_folder(session, drive, folder_id, name) -> WatchedFolder` (takes the page token **before** listing, then calls `initial_sync`); `initial_sync(session, drive, folder) -> SyncResult`; `poll_changes(session, drive, folder, now) -> SyncResult` with `SyncResult(queued: int, deleted: int, unchanged: int)`; routes `GET /api/folders?q=`, `PUT /api/folder`, `GET /api/folder` (incl. `last_synced_at`, counts by status), `POST /api/folder/sync`.

- [ ] **Step 1: Write failing tests:**
  - `test_token_taken_before_listing`: FakeDrive records call order: `start_page_token` comes before `list_folder`.
  - `test_initial_sync_queues_all_supported_files`.
  - `test_change_new_file_in_folder_queued`; `test_change_other_folder_ignored`.
  - `test_change_hash_changed_requeues`; `test_change_same_hash_unchanged`.
  - `test_trashed_marks_deleted`; `test_removed_marks_deleted`.
  - `test_moved_out_of_folder_marks_deleted` (Review Focus 3) — and `v_performance` no longer returns its rows.
  - `test_invalid_page_token_falls_back_to_full_relist`.
  - `test_reconnect_required_sets_folder_error`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(sync): folder selection, initial sync, change polling`

### Task 11: Background wiring and read API

**Files:** Modify `backend/app/main.py`; Create `backend/app/api/{files,documents,observations,funds}.py`; Test `backend/tests/api/test_read_api.py`

**Interfaces:**
- Consumes: everything above.
- Produces (all JSON; decimals as strings):
  - `GET /api/files?status=&q=` (where `q` searches FTS), `POST /api/files/{id}/retry`, `POST /api/files/{id}/reextract`.
  - `GET /api/documents/{id}` → document + funds → facts/observations with `quote_verified`, `needs_review`, `conflict_ids`; `GET /api/documents/{id}/revisions`; `GET /api/files/{id}/content` streams the original bytes (exported PDF/CSV for native files) with the right `Content-Type`, and adds `Content-Security-Policy: sandbox` for HTML.
  - `GET /api/observations?fund_id=&manager=&metric=&period_kind=&start=&end=&needs_review=&format=csv` → rows with `conflict: bool`, source document/page. `GET /api/performance/grid?start=&end=` → `{months: [...], rows: [{fund, manager, cells: {"2026-01": {value, observation_id, conflict}}}]}` using monthly `return`, newest `as_of_date` winning on conflict.
  - `GET /api/funds`, `POST /api/funds/merge {keep_id, merge_id}`.
  - Lifespan: when `start_background`, start `Worker` and an APScheduler `interval(seconds=60)` job calling `poll_changes`; on shutdown stop both.
- [ ] **Step 1: Write failing tests:** seeded DB; one test per endpoint for its filter semantics; `test_grid_prefers_newest_as_of_on_conflict`; `test_csv_export_header_and_percent_format`; `test_html_content_has_sandbox_csp`; `test_reextract_creates_forced_job`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(api): read endpoints, grid, export, background wiring`

### Task 12: Ask agent with read-only SQL

**Files:** Create `backend/app/ask/{sql_guard,agent}.py`, `backend/app/api/ask.py`; Test `backend/tests/ask/test_sql_guard.py`, `test_agent.py`

**Interfaces:**
- Produces: `ReadOnlyQuery(db_path: str)` with `run(sql: str) -> QueryResult(columns: list[str], rows: list[list], truncated: bool)`, raising `QueryRejected(reason)`. It opens `file:{path}?mode=ro`, sets an authorizer allowing only `SQLITE_SELECT`, `SQLITE_READ` on `v_*` and their base tables, and `SQLITE_FUNCTION`, plus a progress handler that aborts after 2 s, and caps rows at 200. `answer_question(messages: list[ChatMessage], client, model, db_path, session) -> Answer(text: str, citations: list[Citation], queries: list[QueryTrace])`, where `Citation(kind: Literal["observation","document"], id: int, page: int | None, label: str)`. `POST /api/ask {messages}` → `Answer`.

- [ ] **Step 1: Write failing tests:**
  - Guard (Review Focus 5): parametrised rejects for `DELETE FROM observation`, `ATTACH DATABASE 'x' AS y`, `SELECT * FROM sqlite_master`, `PRAGMA table_info(fund)`, `SELECT 1; DROP TABLE fund`, `SELECT * FROM google_account`; accepts `SELECT fund, value FROM v_performance ORDER BY value DESC LIMIT 1`.
  - `test_row_cap_truncates`; `test_slow_query_aborts` (a recursive CTE).
  - Agent, with a scripted stub client: `test_tool_loop_returns_citations` — the stub asks for `get_schema`, then `run_sql`, then answers citing `[obs:12]`, and the result has `Citation(kind="observation", id=12, …)` and one `QueryTrace`; `test_stops_after_six_tool_calls`; `test_rejected_sql_is_returned_to_model_as_tool_error`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** The system prompt states the views, enum values, citation syntax `[obs:ID]` / `[doc:ID:p.N]`, the "latest January if no year, and say so" rule, and the conflict rule. Citations are parsed out of the final text and checked to exist; unknown ids are dropped.
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `feat(ask): read-only SQL guard and cited Q&A agent`

### Task 13: Frontend shell, API client and Connect screen

**Files:** Create `frontend/` (Vite React TS template, Tailwind), `src/api.ts`, `src/components/{AppShell,StatusChip,PercentCell}.tsx`, `src/routes/Connect.tsx`; Test `frontend/src/components/*.test.tsx`

**Interfaces:**
- Consumes: Task 9–11 endpoints. Vite proxies `/api` to `127.0.0.1:8000`.
- Produces: typed fetchers in `api.ts` mirroring each endpoint; `<PercentCell value={string|null} />` (renders `1.23%` with two decimals, red when negative, `—` when null); `<StatusChip status />`; app routes `/connect`, `/library`, `/documents/:id`, `/performance`, `/ask`, `/funds`, with a redirect to `/connect` when not connected or no folder is chosen.
- [ ] **Step 1: Write failing tests:** `PercentCell` renders `"0.0123"→"1.23%"`, `"-0.008"→"-0.80%"` with a red class, `null→"—"`; `StatusChip` text and colour for each status.
- [ ] **Step 2: Run** `npm --prefix frontend test` → FAIL. **Step 3: Implement**, including Connect: button → `/api/auth/google/start`; folder search (debounced) → choose → progress ("n of m processed", polling `/api/folder` every 2 s). **Step 4: Run** → PASS, and `npm run build` is clean.
- [ ] **Step 5: Commit** `feat(web): shell, API client, connect flow`

### Task 14: Library and Document detail screens

**Files:** Create `src/routes/{Library,DocumentDetail}.tsx`, `src/components/{SourceViewer,ExtractedPanel}.tsx`; Test `src/routes/Library.test.tsx`, `DocumentDetail.test.tsx`

- [ ] **Step 1: Write failing tests** (MSW mocks): Library lists files with chips, filters by status, and shows "Last synced …" plus a working **Sync now**. Document detail groups values by fund; an unverified value shows a marker; clicking a value calls the viewer's `goToPage(n)`; **Re-extract** posts and refetches.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (react-pdf for PDFs, `<iframe sandbox>` for HTML, a table for CSV). Library refetches every 5 s while any file is queued or processing. **Step 4: Run** → PASS; build clean.
- [ ] **Step 5: Commit** `feat(web): library and document detail`

### Task 15: Performance and Funds screens

**Files:** Create `src/routes/{Performance,Funds}.tsx`, `src/components/SourceLink.tsx`; Test `Performance.test.tsx`, `Funds.test.tsx`

- [ ] **Step 1: Write failing tests:** grid renders months as columns and sorts by a month column; a conflict cell shows the "2 sources differ" marker, which opens both sources; rows mode applies the filters to the query string; **Export CSV** links to `format=csv` with the current filters; Funds selects two and posts a merge.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** with TanStack Table; filters live in the URL query string. **Step 4: Run** → PASS; build clean.
- [ ] **Step 5: Commit** `feat(web): performance grid/rows and funds merge`

### Task 16: Ask screen

**Files:** Create `src/routes/Ask.tsx`; Test `Ask.test.tsx`

- [ ] **Step 1: Write failing tests:** sending a message shows a pending state, then the answer; `[obs:12]` renders as a link to the source document page; "Show query" expands the SQL and rows; suggested questions come from `/api/performance/grid` (latest month).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; build clean.
- [ ] **Step 5: Commit** `feat(web): ask screen with citations`

### Task 17: Synthetic corpus and eval harness

**Files:** Create `evals/generate_corpus.py`, `evals/run_eval.py`, `evals/corpus/*` (generated, committed); Test `backend/tests/test_eval_scoring.py`

**Interfaces:**
- Produces: `score(truth: list[TruthObs], got: list[TruthObs]) -> Scores(precision, recall, by_metric, by_file)`, matching on (normalized fund key, metric, period_kind, period_end) with value tolerance `0.00005`; `make eval` runs the real `ClaudeExtractor` over `evals/corpus` (no Drive) and prints a table plus the quote-verified rate.
- [ ] **Step 1: Write failing test** for `score` (an exact match, a value mismatch counting as both a false positive and a false negative, a missing item, an extra item).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** the generator (reportlab for PDFs, including a two-column layout and one image-only page rasterised via Pillow; HTML emails; wide/long CSVs) covering every case in spec §9, with 5 fictional managers. **Step 4: Run** → PASS; `make eval` completes (needs `ANTHROPIC_API_KEY`).
- [ ] **Step 5: Commit** `feat(evals): synthetic corpus and extraction scoring`

### Task 18: README and end-to-end check

**Files:** Create `README.md`, finish `.env.example`

- [ ] **Step 1: Write the README:** what it does; architecture diagram (from spec §4); setup (Python 3.12 + uv, Node 20; Google Cloud project → enable the Drive API → OAuth consent screen in Testing with yourself as a test user → Web client with redirect `http://127.0.0.1:8000/api/auth/google/callback`; copy `.env.example`); `make dev`; uploading `evals/corpus` to a Drive folder for a demo; the latest `make eval` numbers; key decisions and trade-offs (spec §3 non-goals, polling vs push, `drive.readonly`, SQLite); data-handling note.
- [ ] **Step 2: Run** `make test` → all backend and frontend tests pass; `npm --prefix frontend run build` → clean.
- [ ] **Step 3: Manual end-to-end check** of spec §2 steps 1–6 with a real Drive folder; record anything that fails as a known gap in the README.
- [ ] **Step 4: Commit** `docs: README with setup, decisions and eval results`
