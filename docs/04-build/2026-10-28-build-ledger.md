# SDD ledger — plan: docs/03-implementation-plan/2026-10-28-document-intelligence-plan.md

Spec: docs/02-superpowers-brainstorm/2026-10-28-document-intelligence-design.md (approved + A1–A13). Branch: build/mvp (from main @ docs commits). Testing: Q38 — unit only; integration tests deferred to docs/03-implementation-plan/deferred-integration-tests.md.

## Pre-flight scan

| Tasks | Produces → consumes | Finding |
|---|---|---|
| 1 → all | Settings, get_session, create_app, conftest | Task 1 conftest specifies a pgvector testcontainer — integration, deferred by Q38 |
| 2 → 7,8,10,11,12 | ORM models/enums | consistent names (FileStatus, Measure, PeriodKind, EntityKind, JobStatus, ChunkKind) |
| 3 → 6,8 | parse_value, snap_period_end, ParsedValue | consistent; unit_hint literals match RowOut.unit_hint |
| 4 → 9,13 | kind_for, load_text, is_scanned, clean_html, eml_body | consistent |
| 5 → 6,8,9,14,15 | DocumentExtraction, RowOut, TableOut, CsvMapping, LLMProvider, FakeLLM | recorded spike JSON (`docs/03-implementation-plan/spike/out/cur_*.json`) uses the spike shape (`header_rows`, rows with `value`/`unit`, `calendar_year`), not the plan's lean RowOut/TableOut |
| 6 → 9 | read_tables, apply_mapping, RawTable | consistent |
| 7 → 8,12 | normalize_entity, resolve_fund, known_fund_names | consistent |
| 8 → 9,12,13 | persist_extraction, mark_conflicts | all Task 8 tests need Postgres → deferred |
| 9 → 10 | process_file | tests need DB via persist → deferred; Task 9 "searchable" assert moved to 13 already |
| 10 ↔ 11 | run_worker(poll_fn) ← poll_changes | fixed in plan self-review (poll_fn injected) |
| 11 → 12,14 | current_user, DocumentSource, select_folder, poll_changes | auth/sync tests mostly DB → deferred |
| 12 → 14,16–21 | REST contract, analyze-tagged routes | `test_analyze_routes_have_operation_ids` uses app.openapi() only → stays unit |
| 13 → 21 | simple_search, similar_documents, GET /api/search | DB tests deferred |
| 14 → 21 | build_tools, call_tool, answer_question, POST /api/analyze | loop testable with scripted FakeLLM + stubbed call_tool → unit |
| 15 | match, run_eval | unit; live run needs human approval (cost) |
| 16–21 | web, consumes Task 12–14 JSON | consistent; compose `web` 5173:80 and Vite dev 5173 only collide if both run at once — acceptable |
| 22 | Dockerfiles, CapRover, README, gates | gates: full backend suite = unit only under Q38 |

Per-task self-consistency: Tasks 3,4,5,6,7,15,16–21 self-consistent. Tasks 1,2,8,9,10,11,12,13 specify integration tests that Q38 defers (rulings below). Task 14 self-consistent.

## Pre-flight rulings
- Ruling: Under Q38, any test in Tasks 1,2,8–13 that needs Postgres/testcontainer/network is NOT written; the implementer appends its name + assertions to docs/03-implementation-plan/deferred-integration-tests.md under the task — user's explicit instruction overrides plan text — cost if wrong: DB-level bugs surface only when the user tries the app.
- Ruling: DB-touching tasks extract their decision logic into pure functions and unit-test those instead (Task 8: conflicts(rows)->set, review_reasons(row, as_of)->list, chunk_pages(...); Task 9: route decision; Task 10: backoff(attempts); Task 11: decide_change(change, known_ids, descendant_ids)->Action, crypto round-trip; Task 13: rrf_fuse(...)) — keeps the deferred tests cheap — cost: slightly more functions.
- Ruling: Task 2 verification without a DB = `alembic upgrade head --sql` (offline SQL) must run and contain `CREATE EXTENSION IF NOT EXISTS vector`, `vector(1536)` and the hnsw index — cost: migration not executed against a real DB until the user runs it.
- Ruling: Task 5 converts the recorded spike outputs once into the plan's lean schema (`header`, rows without `value`, `unit_hint`, `calendar_year`→`1y` ending 31 Dec, AUM/NAV/account period_kind→`other`) and commits them as backend/tests/recorded/<file>.json — plan schema wins over spike shape — cost: recorded data is a transformation, not raw model output.
Task 1: dispatched (BASE 745b813, sonnet)
Task 1: implementer DONE 818630b; review dispatched (sonnet)
Task 1: review — 2 Important (worker path app.worker→app.jobs.worker; eval path evals.run→evals.run_eval); ⚠️ Dockerfiles + nginx /api proxy → confirmed owned by Task 22
Task 1: minor (deferred): empty-string defaults for session_secret/fernet_key/openai_api_key → validate when auth (Task 11) consumes them
Task 1: minor (deferred): compose env_file .env required → consider required:false
Task 1: minor (deferred): compose publishes 5432 (may clash with local Postgres)
Task 1: minor (deferred): db.py builds engine at import from settings
Task 1: fix round 1/5 (2 addressed, 0 open; commits 818630b..30c6117)
Task 1: complete (commits 745b813..30c6117, review clean after 1 fix round)
Task 2: dispatched (BASE 30c6117, sonnet)
Task 2: implementer DONE_WITH_CONCERNS 3a3adde
Ruling: Task 2 "11 tables" in plan is a miscount; the enumerated list has 10 — build the 10 listed — cost if wrong: a forgotten 11th table surfaces in a later task's interface (none references one)
Ruling: Task 2 enum columns stored as String (StrEnum Python-side), not Postgres ENUM types — simpler migrations; values still validated in code — cost: DB doesn't reject bad strings
Task 2: review Approved (spec ✅); ⚠️ migration-vs-ORM sync unverifiable without DB → resolved: added to deferred tests list (alembic check / metadata compare); ⚠️ settings import in subprocess → accepted on implementer's 9/9 evidence
Task 2: minor (deferred): redundant ix_watched_folder_user_id alongside unique(user_id)
Task 2: minor (deferred): alembic env.py engine not disposed; no compare_type; alembic.ini logging unused
Task 2: minor (deferred): test_schema local import + hard-coded PATH in subprocess
Task 2: minor (deferred): no CHECK constraints on string enum columns
Task 2: complete (commits 30c6117..3a3adde, review clean)
Task 3: dispatched (BASE e28104c, sonnet)
Task 3: implementer DONE ac0e555; review dispatched
Task 3: review Approved (spec ✅); ⚠️ PeriodKind.y1/qtd/ytd exist — confirmed by grep in models.py
Task 3: minor (deferred, FLAG for final review — wrong value): parse_value("$5","percent") divides by 100 then labels currency
Task 3: minor (deferred, FLAG for final review — drops negatives): en-dash minus "–0.45%" from PDFs returns None (bare dash must stay placeholder)
Task 3: minor (deferred): "+" removed anywhere not just leading; lax thousands separators "1,,2"; -0 rendering; redundant unit override; extra test cases (GBP, negative bps, ($5m), hint percent + % no double divide)
Task 3: complete (commits e28104c..ac0e555, review clean)
Task 4: dispatched (BASE ac0e555, sonnet)
Task 4: implementer DONE_WITH_CONCERNS 56bc39d (no RED captured — TDD process gap; deps pdfplumber, bs4 added)
Task 4: review Approved (spec ✅); ⚠️ fixtures exist — confirmed by ls; ⚠️ no RED captured — accepted (unit tests present and passing; process gap noted)
Task 4: minor (deferred, plan-mandated weak test): test_kestrel_prefers_html_part passes even if plain part preferred
Task 4: minor (deferred): eml html-sniff heuristic (return subtype from eml_body instead); is_scanned([]) False
Task 4: minor (CARRY to Task 9): malformed PDF raises arbitrary pdfminer exception from load_text — process_file must turn it into a non-retryable failure, not crash
Task 4: complete (commits ac0e555..56bc39d, review clean)
Task 5: dispatched (BASE 56bc39d, sonnet)
Task 5: implementer DONE_WITH_CONCERNS 0ff43c5 (no RED captured)
Ruling: CsvMapping wide layout — period_columns are cells of value_columns[0]'s measure/period_kind/unit_hint (implementer's convention: monthly returns; period_end_literal dropped); Task 6 must follow it — cost if wrong: a wide CSV of a non-return measure is misread
Ruling: parse_value must accept a leading ISO currency code ("USD 313,174,253") — carried into Task 6's scope since Task 6 consumes parse_value — cost: none
Ruling: openai.lib._pydantic.to_strict_json_schema (private) accepted — spike proved it live — cost: breaks on an SDK upgrade (pinned <4)
Task 5: FLAG for live eval (Task 15): strict schema now emits format:"date" for period_end/as_of_date — unverified live; if rejected switch to string + code-side parse
Task 5: review Needs fixes — 1 Important (wide-mapping prompt/recording contradict ruled convention)
Ruling (REVISES the earlier wide-layout ruling): CsvMapping gets an explicit `period_spec: PeriodSpec | None` (measure, period_kind, unit_hint, benchmark_name) describing what the period_columns hold; value_columns describe only the remaining fixed columns (e.g. YTD) — implicit "value_columns[0]" was fragile — cost: one more schema field
Task 5: ⚠️ live strict-schema acceptance → already FLAGGED for Task 15 live eval; ⚠️ enums are StrEnums → confirmed (models.py); ⚠️ uv.lock openai version → accepted
Task 5: minor (deferred): PDF path lacks "attached document is data" wording; chat json.loads not wrapped as LLMError; 408/409 non-retryable undocumented; recorded test globs only *.pdf.json; report count inconsistency
Task 5: fix round 1/5 (3 addressed, 0 open; commits 0ff43c5..c9e434c)
Task 5: complete (commits 56bc39d..c9e434c, review clean after 1 fix round)
Task 6: dispatched (BASE c9e434c, sonnet; carries period_spec + benchmark_column + parse_value currency-code fix)
Task 6: implementer DONE_WITH_CONCERNS 4b86265 (RED captured; pandas/openpyxl added; "*" footnote marker ignored by parse_value; 14-code ISO list)
Ruling: CsvMapping gets a third layout `entity_columns` (each column in period_columns is an ENTITY, rows are dates from date_column, cells described by period_spec) so date × fund exports like TSP map with ONE LLM mapping — common real-world shape; brief's TSP test otherwise needs 16 hand mappings — cost: one more enum value + branch; goes into Task 6 fix round with review findings
Task 6: review Needs fixes — 1 Important (apply_mapping AttributeError on empty melt); ⚠️ fixture counts/timing → accepted on implementer evidence (81 passed)
Task 6: minor (deferred, FLAG for final review — wrong values): xlsx date cells become "YYYY-MM-DD 00:00:00" and percent-formatted cells arrive as raw fractions (percent hint → 100x too small)
Task 6: minor (deferred): double "*" strip; silent drops of unparseable cells/dates (no count/log); no cp1252 fallback; ISO list omits INR/ZAR/BRL/...; duplicate headers bind first; TSP test loose asserts; empty entity skipped silently
Task 6: fix round 1/5 (2 addressed, 0 open; commits 4b86265..91de40e)
Task 6: minor (deferred): entity_columns mapping with value_columns not rejected
Task 6: complete (commits c9e434c..91de40e, review clean after 1 fix round)
Task 7: dispatched (BASE 91de40e, sonnet)
Task 7: implementer DONE c6225ff (concern: empty normalized key e.g. 'The Fund')
Task 7: review Needs fixes — 1 Important (empty normalized key merges unrelated funds); ⚠️ test file location → confirmed: unit tests under tests/unit, integration ones in deferred doc (per Q38)
Ruling: Task 7 concurrent-insert race (reviewer Minor) promoted into fix round — worker concurrency 3 on first sync makes two workers resolving one new fund likely; an IntegrityError would fail a document — fix with a savepoint + re-read — cost: small code
Task 7: minor (deferred): resolve_fund loads all aliases per call (use keyed lookup); "L P" token pairing; manager not updated on later resolves
Task 7: fix round 1/5 (2 addressed, 0 open; commits c6225ff..5a924ce)
Task 7: minor (deferred): punctuation-only names still yield empty key
Task 7: complete (commits 91de40e..5a924ce, review clean after 1 fix round)
Task 8: dispatched (BASE 5a924ce, sonnet)
Task 8: implementer DONE_WITH_CONCERNS 1f32df8 (DB wrappers unexercised per Q38; conflicts only across documents; ±50% for return/benchmark/account monthly)
Task 8: review Approved (opus); ⚠️ callers of persist/mark_conflicts → CARRY to Task 9 (call mark_conflicts after each persist); ⚠️ DB path unexercised → deferred by Q38
Task 8: minor (deferred, FLAG for final review — global constraint): store.py:303 update and store.py:223 Document select lack user_id predicate (safe today via scoped ids)
Task 8: minor (CARRY to Task 9): NUL bytes in PDF text would make Postgres reject page_texts/chunk text — strip \x00 when building LoadedText
Task 8: minor (deferred): only one review reason kept (elif); entity_kind not in conflict key; test hygiene (FileKind.__args__, loose `in` asserts); ruff never run
Task 8: complete (commits 5a924ce..1f32df8, review clean)
Task 9: dispatched (BASE 1f32df8, sonnet; carries malformed-PDF failure, NUL strip, mark_conflicts call)
Task 9: implementer DONE_WITH_CONCERNS fec33fc
Ruling: CSV head "skip" = count of leading blank rows (mapping's skip_top unknown before the mapping call); head = skip+20 rows, tail = last 5 — preamble rows (Alderbank title lines) still fall inside the head, so the model sees them — cost: a CSV with >20 preamble rows hides its header from the model
Task 9: review Approved; ⚠️ process_file DB glue untested → deferred by Q38; ⚠️ persist sets status → confirmed by reviewer (store.py:264-266)
Task 9: minor (deferred): failed/unsupported/scanned branches leave stale rows from an earlier extraction (re-extract after failure only); unsupported error-message branching; useless test_status_enum_values_used; duplicate garbage-pdf test; misleading test names
Task 9: complete (commits 1f32df8..fec33fc, review clean)
Task 10: dispatched (BASE fec33fc, sonnet)
Task 10: implementer DONE_WITH_CONCERNS 7fadb91
Ruling: job attempts increment at claim (so a reclaimed expired lease counts as an attempt) — bounds crash loops on a file that kills the worker — cost: a worker restart mid-job uses up one of the 3 attempts
Task 10: review Needs fixes (opus) — 3 Important: lease 15 min < worst-case runtime (SDK max_retries=2 × 600 s) → double processing; enqueue check-then-insert race; expired-lease reclaim never hits the attempt cap
Ruling: "3 attempts" = 1 try + 3 retries (backoff 30/120/600 s then failed on the 4th) — matches the brief's wording — cost: one extra LLM attempt per permanently failing file
Ruling: Task 10 minors "SIGTERM shutdown" and "missing SourceFile → PermanentError" promoted into fix round — docker stop is the deploy path; both one-liners — cost: none
Task 10: minor (deferred): force enqueue while running; worker loop crash-survival not unit-tested; is_claimable mirrors SQL by hand; Drive source errors need retryable attr (→ Task 11); no lint
Task 10: fix round 1/5 (5 addressed, 0 open; commits 7fadb91..173114c)
Task 10: minor (deferred, FLAG for final review): lost-lease branch commits stale pipeline writes — should rollback
Task 10: minor (deferred): lease-expiry deadlock (self-recovering); deferred doc says 15 min lease (now 45); SIGTERM join timeout 5 s drops in-flight jobs until lease expiry
Task 10: complete (commits fec33fc..173114c, review clean after 1 fix round)
Task 11: dispatched (BASE 65c0a0a, opus — auth/security-sensitive)
Task 11: implementer DONE_WITH_CONCERNS 109c478 (180 unit tests; 16 DB tests deferred; manual step 6 for human)
Ruling: on a successful OAuth callback for an existing user, re-enqueue that user's files that failed with the reconnect error — weekly Testing-mode expiry (A6) would otherwise leave every file failed needing manual Retry — cost: small; goes into the Task 11 fix round
Ruling: PUT /api/folder (folder change) also deletes the user's fund + fund_alias rows — otherwise /api/funds lists funds from the old folder — cost: none (funds are re-resolved on extraction)
Ruling: needs_reconnect committed inside credentials_for (survives caller rollback) — intended: the flag must persist even when the job fails — cost: none
Ruling: PKCE verifier kept in the signed (not encrypted) session cookie — it is single-use, server-side flow, cookie HttpOnly — cost: a stolen cookie mid-flow could complete that one sign-in
Task 11: review Needs fixes (opus) — 1 Important: watched folder set never shrinks; a subfolder moved out stays watched (probe confirmed)
Task 11: ⚠️ watched_folder.user_id unique → confirmed in Task 2 review (one folder per user); ⚠️ cascade source_file→job/document→chunks → all FKs ON DELETE CASCADE per Task 2 review; ⚠️ manual step 6 → human, at Task 22
Ruling: Task 11 minors "folder_id validation" and "404 → 400 on PUT /api/folder" promoted into the fix round — security hardening + correct status code, both tiny — cost: none
Task 11: minor (deferred): last_error stores raw exception text; no single-use-state test; concurrent first PUT /api/folder; row lock held across Drive calls in sync_now
Task 11: fix round 1/5 (5 addressed, 0 open; commits 109c478..a8178fa)
Task 11: minor (deferred): one re-walk per remove_folder change (batch quota); reconnect selection by error substring; E303 blank lines
Task 11: complete (commits 65c0a0a..a8178fa, review clean after 1 fix round)
Task 12: dispatched (BASE a8178fa, sonnet)
Task 12: implementer DONE_WITH_CONCERNS e9e24b7 (205 unit tests; SQL compile-checked only)
Ruling: files.updated_at = source_file.created_at (no updated column) — cost: Library "updated" shows discovery time
Ruling: rows `fund` filter: all digits → fund_id, else case-insensitive substring on entity — cost: a fund literally named with digits only needs the id
Ruling: extra `missing_in_drive` on file items accepted — needed for the D6 "No longer in Drive" state — cost: none
Ruling: web lane starts only after Task 12 review passes (contract may change in a fix round) — cost: a little wall-clock
Task 12: review Needs fixes (opus) — 2 Important: non-canonical decimal strings (scale-10 / exponent); content sandbox only for exact text/html (SVG/XHTML XSS at app origin, no nosniff)
Task 12: ⚠️ SQL never executed → deferred by Q38 (Task 12 entries incl. test_rows_filter_january_2026_sorted)
Ruling: Task 12 minor "isdigit → int() 500 on '²'" promoted into fix round — a user-reachable 500 — cost: none
Task 12: minor (deferred): ILIKE patterns not escaped (% _); get_document + meta inline queries lack compiled user_id tests; redundant startswith guard; no lint
Task 12: fix round 1/5 (3 addressed, 0 open; commits e9e24b7..28ed566)
Task 12: complete (commits a8178fa..28ed566, review clean after 1 fix round)
LANE: web worktree ../equi-web on branch lane/web from 28ed566 (Tasks 16–21 in parallel with 13–15, per user's CLAUDE.md lane rule)
Ruling: parallel implementers only across separate worktrees (main: 13–15; lane/web: 16–21) — user's CLAUDE.md mandates parallel lanes; separate worktrees remove file conflicts — cost: merge at the end
Task 13: dispatched (BASE 28ed566, sonnet, main checkout)
Task 16: dispatched (BASE 28ed566, sonnet, worktree ../equi-web lane/web)
Task 13: implementer DONE_WITH_CONCERNS 4a3b309 (no clean RED; SQL compile-checked only)
Ruling: vector hits limited by MAX_COSINE_DISTANCE = 0.65 so Find can return "no results" — FLAG to tune on first real run (user testing / Task 22) — cost if wrong: too few or too many weak matches
Ruling: get_llm dependency caches OpenAIProvider on app.state.llm (overridable in tests) — cost: none
Task 13: review Needs fixes — 1 Important: similar fund matching stringifies {name, share_class} dicts
Ruling: Task 13 minor "embedding failure → 500" promoted into fix round: fall back to full-text only — Find must work when OpenAI is down — cost: none
Task 13: minor (deferred, FLAG live EXPLAIN at Task 22): vector ORDER BY dist, id tie-break may defeat HNSW; per-call avg over all user chunks; stopword-only query untested
Task 13: fix round 1/5 (2 addressed, 0 open; commits 4a3b309..eff8860)
Task 13: minor (deferred): import order in search/service.py; plain-string fund names with class suffix not stripped
Task 13: complete (commits 28ed566..eff8860, review clean after 1 fix round)
Task 14: dispatched (BASE eff8860, opus — security-relevant tool loop)
Task 16: implementer DONE_WITH_CONCERNS d33ee0c (lane/web; 32 tests; build clean; page bodies stubbed for 17–21; loose search/analyze types)
Ruling: replace the third-party npm package "cn" (^0.5.0) with the standard shadcn local helper (src/lib/utils.ts: clsx + tailwind-merge) — unvetted dependency in every UI component is a supply-chain risk and non-standard — cost: none
Task 16: review Needs fixes — Important: third-party `cn` pkg (ruled); SearchHit loosely typed vs real Task 13 shape; stack drift (React 19 / Tailwind 4 / Vite 8 vs plan's React 18 / Tailwind 3)
Ruling: accept React 19 + Tailwind 4 (CSS-first @theme, no tailwind.config.ts) — current shadcn default; builds clean; plan's file list amended in Task 22 README/decisions — cost: plan text mentions tailwind.config.ts
Ruling: Task 16 minors "global 401 → /connect" and "formatMoney negative zero" promoted into fix round — expired sessions (7-day Testing mode) otherwise degrade silently — cost: small
Task 16: ⚠️ last_synced_at tz → checked models (DateTime timezone-aware) — ISO carries offset; ⚠️ analyze endpoint shape → provisional until Task 14; ⚠️ tests/build → implementer evidence
Task 16: minor (deferred): Intl RangeError on bad currency; exponent strings render "—"; SearchBox not synced on back/forward; relativeTime NaN guard; theme 'system' not live; oxlint extra
Task 16: fix round 1/5 (4 addressed, 0 open; commits d33ee0c..0d28bf3)
Task 16: minor (deferred): AnalyzeResponse provisional types (tighten after Task 14)
Task 16: complete (commits 28ed566..0d28bf3 on lane/web, review clean after 1 fix round)
Task 17: dispatched (BASE 0d28bf3 lane/web, sonnet)
Task 14: implementer DONE_WITH_CONCERNS e333803 (242 unit tests)
Task 14: FLAG for live run (Task 15 / user testing): Analyze loop resends tool calls without the model's reasoning items — if gpt-6.1-terra requires them, chain with previous_response_id or carry raw output in ChatTurn
Ruling: final Analyze answer as JSON-in-text with text-only fallback (chat() has no format param) — cost: occasional table lost on malformed JSON
Ruling: POST /api/analyze also tagged `analyze`; tool builder takes GET-only so it is never a tool; operation-id test narrowed to GET — cost: none
Task 17: implementer DONE_WITH_CONCERNS b1398e0 (40 tests; build clean)
Ruling: C2 not-allowed alert uses generic wording (email not passed in URL) — avoids putting the rejected address in a URL — cost: less specific message
Ruling: C4 shows Progress + /library link only (no per-file table, no Sync now on Connect) — brief scope; Library has both — cost: none
Task 17: minor (deferred, backend): "Use another Google account" needs prompt="select_account consent" on /api/auth/google/start
Task 14: review Needs fixes (opus) — 1 Important: 60 s budget doesn't bound the 600 s threadpool LLM call; LLMError/IncompleteResponse/bad tool JSON → bare 500
Ruling: Task 14 minors "path param validation", "tool route exceptions → 500", "huge source ids → 500" promoted into fix round — user-reachable 500s and a latent path escape; all small — cost: none
Task 14: minor (deferred): useless test_tool_error_class_exported; steps echo model text (web lane must render as text — React does by default)
Task 17: review Needs fixes — 1 Important: stale connect-me cache (has_folder:false) lets a replace skip the destructive confirm
Task 17: ⚠️ confirm copy → confirmed: folder change deletes the user's files/documents (cascade) + funds (Task 11 fix round); ⚠️ mockup fidelity → eyeball at user testing
Task 17: minor (deferred): AlertDescription span layout; ' ' spacer; 2.5 s real-timer wait in test; handles401 on FirstSync shows error not redirect
Task 17: fix round 1/5 (2 addressed, 0 open; commits b1398e0..b52fbbd)
Task 17: minor (deferred, FLAG final review): stop-polling assertion vacuous (fake timers enabled after interval scheduled); remount test has no RED
Task 17: complete (commits 0d28bf3..b52fbbd on lane/web, review clean after 1 fix round)
Task 18: dispatched (BASE b52fbbd lane/web, sonnet)
Task 14: fix round 1/5 (4 addressed, 0 open; commits e333803..5458900)
Task 14: minor (deferred): no explicit "budget spent → stop" before a call (1 s floor); malformed args echoed as {}; tool calls' 30 s httpx timeout not tied to budget
Task 14: complete (commits eff8860..5458900, review clean after 1 fix round)
Task 15: dispatched (BASE 5458900, sonnet; live run NOT executed — needs human approval for spend)
Task 18: implementer DONE_WITH_CONCERNS 3a7d0ae (51 tests; build clean)
Ruling: Library filters = status only (spec §8 lists filters on the Data table, not Library) — cost: mockup's doc type/manager/fund chips absent
Task 18: minor (deferred, FLAG final wave — cross-lane): "Open folder in Drive" needs drive_folder_id from GET /api/folder to deep-link (currently my-drive)
Task 18: ⚠️ "Choose a different folder" → confirmed Connect has a Change folder path with confirm (Task 17)
Task 18: review Needs fixes — 5 Important: status filter not in URL; misleading Drive button; folder 404/error unhandled; Sync now doesn't invalidate files; mutation errors dropped
Ruling: remove "Open folder in Drive" until the final wave adds drive_folder_id to GET /api/folder (then restore as a real deep link) — a button that doesn't open the folder misleads — cost: one action missing for now
Task 18: minor (deferred): tags read concatenated by screen readers; row click mouse-only; StatusBadge throws on unknown status; test counts helper; selected status chip can vanish at 0
Task 15: implementer DONE_WITH_CONCERNS 416d1ce (270 unit tests; live run NOT executed — awaits human approval; eval-results.md pending)
Task 15: review Needs fixes — 1 Important: matcher lets one got row satisfy several truth rows (inflated recall)
Ruling: Task 15 minors "empty-entity-token match", "one non-LLM error kills the paid run", and the brief's missing "total cost" promoted into fix round — protects the paid run's integrity; price table from spike findings (sol $2/$10, terra $1/$5 per 1M, embeddings small) — cost: prices may drift; printed as an estimate
Task 15: minor (deferred): per-measure recall re-globs truth; error text from provider printed; python-dotenv undeclared
Task 18: fix round 1/5 (6 addressed, 0 open; commits 3a7d0ae..6a61d7d)
Task 18: minor (deferred): Retry error <p> inside clickable row bubbles to navigation; Connect dead-end if has_folder true but /api/folder 404
Task 18: complete (commits b52fbbd..6a61d7d on lane/web, review clean after 1 fix round)
Ruling: Document view for .xlsx shows "Preview not available — see As printed" in the file pane (no in-browser spreadsheet renderer; each sheet is already a printed table) — cost: no raw xlsx preview
Task 19: dispatched (BASE 6a61d7d lane/web, sonnet)
Task 15: fix round 1/5 (4 addressed, 0 open; commits 416d1ce..64d0652)
Task 15: minor (deferred): greedy matching order can understate recall (sort classed truth rows first); cost column unlabelled in header; ERROR rows show no per-doc cost; per-measure recall double-counts duplicate keys
Task 15: complete (commits 5458900..64d0652, review clean after 1 fix round)
BACKEND LANE DONE: Tasks 1–15 complete on build/mvp @ 64d0652. Live `make eval` awaits user approval.
Task 19: implementer DONE_WITH_CONCERNS 359b3a7 (71 tests; build clean w/ chunk-size warning)
Ruling (cross-lane contract fix, "Task 12b"): backend adds `document_id` (nullable) and `drive_file_id` to GET /api/files items; GET /api/documents/{id} gains a `file` object {id, status, error, missing_in_drive, mime_type, kind, path, drive_file_id}; GET /api/folder gains `drive_folder_id`. Web links Library rows → /documents/{document_id} (no document → no link; error + Retry stay inline), uses the embedded file object, and restores "Open in Google Drive" (file: drive.google.com/file/d/{id}/view; folder: drive.google.com/drive/folders/{id}) — Library linked by file id while the API takes document id (wrong document opened) — cost: one small backend change on build/mvp
Task 12b: dispatched (BASE 64d0652, sonnet, main checkout)
Task 12b: implementer DONE 4264659 (279 unit tests); review dispatched
Task 19: review Needs fixes — 3 Important: no polling after Re-extract/Retry (+ double re-queue); `gone` leaks across route params; pdf.js in main bundle
Ruling: .eml content — backend GET /api/files/{id}/content serves the email's HTML body (eml_body) as text/html (still nosniff + CSP sandbox) for message/rfc822 — browsers download/raw-show rfc822 in an iframe — cost: small backend change ("Task 12c") after Task 12b review
Ruling: Task 19 fix round also switches to the 12b contract (document_id links from Library, embedded file object, Open in Google Drive for file + folder) and takes cheap minors: drop always-"—" Fund cell, type DocumentDetail.funds properly, keep picker selection across tab switches
Task 19: minor (deferred): table captions; keyboard tests; "+—"/"+0.00%" sign; CSV row cap; probe double request; pdf cMap/standard fonts; pdfjs-dist transitive
Task 12b: review Approved; minor (deferred): test_get_document_query_scoped_and_404 name overstates (no SQL assert)
Task 12b: complete (commits 64d0652..4264659, review clean)
Task 12c: dispatched (BASE 4264659, sonnet): .eml content served as its HTML body; prompt="select_account consent" (Task 17 minor)
Task 12c: implementer DONE b4a1f86 (282 unit tests); review dispatched
Task 19: fix round 1/5 (5 addressed, 0 open; commits 359b3a7..c7a3695)
Task 19: minor (deferred): Drive URLs interpolate ids without encodeURIComponent; split act import; PdfPane 404 probe redundant with missing_in_drive
Task 19: complete (commits 6a61d7d..c7a3695 on lane/web, review clean after 1 fix round)
Task 20: dispatched (BASE c7a3695 lane/web, sonnet)
Task 12c: review Approved; minor (deferred): import order (files.py, test_read_api.py); no eml size cap; malformed eml → 500; no "<pre> not in HTML" assert; remote images load in sandboxed email
Task 12c: complete (commits 4264659..b4a1f86, review clean)
Task 20: implementer DONE_WITH_CONCERNS 87075a5 (89 tests; build clean)
Ruling: sources-differ tooltip lists only conflicting rows on the current page (API returns flags, not partner rows) — cost: a partner row on another page isn't named; the marker still shows; fix later with a per-row conflict query if wanted
Ruling: @tanstack/react-table pinned 8.21.3 (9.x API differs); cmdk added for shadcn Command — cost: none
Task 20: review Approved; ⚠️ tests/build → implementer evidence; cmdk polyfills live only in DataTable.test (share in setup if reused)
Task 20: minor (deferred): offset beyond total shows misleading empty state; red colour for -0.00%; columns rebuilt per page; start>end unguarded; no end-to-end "best January" test
Task 20: complete (commits c7a3695..87075a5 on lane/web, review clean)
Task 21: dispatched (BASE 87075a5 lane/web, sonnet)
Task 21: implementer DONE cc1fcb6 (96 tests; build clean)
Task 21: review Approved; minor (deferred): similar query key shares search key space; similar loading skeleton untested; analyze error re-POSTs on revisit
Task 21: complete (commits 87075a5..cc1fcb6 on lane/web, review clean)
LANE MERGED: lane/web → build/mvp at e7a82b5 (no conflicts; backend 282 passed; web 96 passed; build clean). Worktree removed, lane branch deleted.
Task 22: dispatched (BASE e7a82b5, sonnet)
Task 22: implementer DONE_WITH_CONCERNS 051b885 (ruff clean; 282 + 96 tests; build ok; compose build ok; alembic upgrade head OK on real pgvector Postgres: 10 tables + alembic_version)
Ruling: ruff ignores E501 (219 long lines in tests/prompts) — reflowing prompts changes model input — cost: long lines allowed
Ruling: compose db port ${DB_PORT:-5432} — host 5432 may be taken — cost: none
Task 22: review Needs fixes — 1 Important: api/worker images run as root
Ruling: Task 22 minors promoted into fix round (all small, deploy-path): CapRover definitions use dockerfilePath to the real Dockerfiles (no duplicated Dockerfile lines); nginx Host $http_host; FORWARDED_ALLOW_IPS documented/set for api; "deploy api before web" in deploy README; ruff known-third-party alembic — cost: none
Task 22: fix round 1 implementer DONE d7ce33a
Task 22: controller check — built backend image contains no .env* files (find /); minor: .dockerignore lacks .env.* pattern; .pytest_cache/.ruff_cache copied into image
Task 22: fix round 1/5 (5 addressed, 0 open; commits 051b885..d7ce33a)
Ruling: move captain-definition-{api,worker,web} to the repo root (final fix wave) so "./backend/Dockerfile" resolves the same whether CapRover reads dockerfilePath relative to the definition or to the tarball root — removes the unverified ambiguity before the live deploy — cost: three files at repo root
Task 22: minor (deferred → final wave): .dockerignore `**/.env*` + `!.env.example`; caches copied into image; APP_ROLE typo silently runs api; api+worker built twice in compose
Task 22: complete (commits e7a82b5..d7ce33a, review clean after 1 fix round)
ALL 22 TASKS COMPLETE (+12b, 12c). Final whole-branch review next.
FINAL REVIEW (opus): Not ready → ready after fixes. Critical: Library crashes on object funds; whole-table embedding chunk exceeds 8,192 tokens (TSP fails). Important: unbounded document rows/printed tables; header shape string[] vs string[][]; mark_conflicts race; MIME-only routing; Drive change without fileId stalls sync; formatMoney RangeError + no error boundary; en-dash negatives dropped.
Ruling: one fix wave = Critical 1–2 + Important 3–9 + ledger "fix now"/wave items (captain-definitions to repo root; .dockerignore **/.env*; lost-lease rollback; percent hint skipped when a currency is present; compose worker waits for api health so migrations run first) — final review triage; everything else stays deferred — cost: one larger dispatch
FINAL WAVE: dispatched (BASE d7ce33a, opus)
FINAL WAVE: DONE d7ce33a..166f5b0 (313 backend, 108 web, build + compose build ok); scoped re-review dispatched
FINAL WAVE: re-review clean (all 14 addressed); minor (deferred): _cap_tokens sub-pieces lose header; misleading log when job row missing; plan docs reference old captain-definition path. Gates (controller-run): ruff clean, 313 backend, 108 web, build ok, compose build ok.
