# Document Intelligence Web App — Design (v0, Claude-only)

> **Provenance.** This is the **blind pass**: Claude wrote it from the take-home
> brief alone, with no input from the user, no brainstorm and no look at any of
> the user's other code. Every decision below is Claude's call. It is kept
> unedited as the baseline that later versions (human brainstorm, guided
> superpowers brainstorm) are compared against. See `docs/README.md`.
>
> **Skipped on purpose:** the rendered UI mockup that normally comes before a
> spec, and the builder-check review. Both need the user's input, and this pass
> has none. Screens are described in prose in §7.

## 1. Intent

An allocator gets performance documents from many fund managers: factsheets,
monthly statements, performance reports, investor-update emails, CSV exports.
No two look alike. Today someone reads each one and types the numbers into a
spreadsheet. The app replaces that: point it at a Google Drive folder, and every
document in it — and every document dropped in later — turns into rows in one
table you can filter, compare and ask questions about.

The value isn't in "an LLM read a PDF". It's in **trust**: an allocator will
act on a number only if they can see where it came from. So every extracted
number carries its source (document, page, verbatim quote), and the app says
plainly when it is unsure or when two sources disagree.

## 2. Success looks like

The brief's own scenario, end to end, on a fresh machine:

1. Run one command, open the app, click **Connect Google Drive**, sign in.
2. Pick a folder holding ~20 messy documents from different managers.
3. Within a couple of minutes the **Performance** table fills in: fund, manager,
   period, return, benchmark, source document.
4. Filter to "January 2026, monthly returns", sort, and see the best fund.
5. Ask "Which fund had the best January return?" and get an answer with a
   citation that opens the source document at the right page.
6. Drop a new factsheet into the Drive folder. Within about a minute it shows
   up as processing, then its numbers appear — no clicks.

## 3. Goals, non-goals, anti-goals

**Goals**
- Ingest PDF, HTML (including saved `.html` emails), `.eml`, CSV, and
  Google-native Docs/Sheets (exported to PDF/CSV) from one Drive folder.
- No per-manager configuration. One generic extraction path per file kind.
- Extract a canonical record: funds, performance observations (monthly, QTD,
  YTD, 1Y, 3Y, 5Y, since inception), benchmark returns, AUM/NAV, and key terms
  (strategy, fees, liquidity) as facts.
- Provenance on every value: page (or CSV row/column) plus a verbatim quote,
  checked against the document's text.
- Automatic sync: new and changed files are picked up; deleted files drop out.
- Browse (documents, funds), filter (fund, manager, metric, period, date),
  full-text search, and natural-language Q&A with citations.
- A small evaluation harness with ground truth, so extraction quality is a
  number rather than a feeling.

**Non-goals** (rough edges are fine here)
- Production deployment, CI/CD, multi-tenant accounts, horizontal scaling.
- Sub-folders (top level of the chosen folder only).
- Excel `.xlsx` files, password-protected PDFs, documents over 50 pages.
- Drive push notifications (they need a public HTTPS endpoint; polling is used).
- Editing extracted values in the UI (re-extract and fund merge only).

**Anti-goals** (would be a failure even if it "works")
- A number shown with no way to trace it to its source.
- Silently picking one value when two documents disagree about the same fund
  and period.
- Percent/decimal confusion (0.8% stored as 0.8 or 80%) — this is the most
  likely error to cause a bad decision.
- The Q&A making up an answer the data doesn't support, or being able to
  change data.
- Anything that needs the user to write a parser, template or mapping.

## 4. Architecture

```
 Google Drive ──(OAuth, drive.readonly)──► Sync poller (60s, Changes API)
                                                │ upsert source_file, enqueue job
                                                ▼
                                    jobs table (SQLite) ◄── worker thread
                                                │
                     ┌──────────────────────────┼─────────────────────────┐
                     ▼                          ▼                         ▼
              PDF / Google Doc            HTML / .eml                CSV / Sheet
       text layer + PDF to Claude     cleaned text to Claude   header+sample → Claude
                     │                          │              returns column mapping;
                     └──────────► DocumentExtraction ◄─────── pandas applies it
                                                │
                       normalise values · verify quotes · resolve funds
                                                ▼
                     SQLite: documents, funds, observations, facts, FTS
                                                ▼
                FastAPI JSON API  ──►  React UI (Library, Performance, Ask, Funds)
                                                ▲
                       Ask agent: Claude + read-only SQL over views + FTS search
```

**Stack (Claude's call):**
- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0, SQLite (WAL mode, FTS5),
  pandas, pdfplumber, BeautifulSoup, Google API client, Anthropic SDK. Managed
  with `uv`. Python because the brief says the team uses Python, pandas and
  SQLAlchemy; SQLite because it's one file, needs no setup, and is plenty for a
  single user — the SQLAlchemy layer keeps Postgres a config change away.
- **Background work:** one in-process worker thread pulling from a `jobs` table,
  plus an APScheduler interval job for sync. No Redis/Celery: one user, one
  process, and a DB-backed queue survives restarts.
- **Frontend:** React + TypeScript + Vite, TanStack Query and TanStack Table,
  Tailwind. A real table with sorting and filtering is the core screen;
  Streamlit would fight that.
- **LLM:** Claude. `claude-sonnet-5-5` for extraction and Q&A. Structured
  output via a single forced tool call with a JSON schema, validated by
  Pydantic. Model and prompt version are stored with every extraction.
- **One command:** `make dev` runs backend and frontend; `make eval` runs the
  extraction eval.

## 5. Data model

| Table | Purpose / key columns |
|---|---|
| `google_account` | one row; email, Fernet-encrypted token JSON, scopes |
| `watched_folder` | one row; Drive folder id/name, `changes_page_token`, `last_synced_at`, `last_sync_error` |
| `source_file` | one per Drive file; `drive_file_id` (unique), name, mime type, `content_hash` (md5Checksum, or `version` for native files), modified time, `status` (`queued`·`processing`·`done`·`needs_review`·`failed`·`unsupported`·`deleted`), `error` |
| `document` | one per *revision* of a file; `source_file_id`, `content_hash`, `is_current`, `doc_type` (`factsheet`·`statement`·`performance_report`·`investor_letter`·`other`), manager, `as_of_date`, base currency, one-line summary, page texts (JSON), model, `prompt_version` |
| `fund` | `canonical_name`, manager, strategy, `normalized_key` (unique) |
| `fund_alias` | `fund_id`, alias, `normalized_key` (unique) — created by extraction and by merges |
| `observation` | `document_id`, `fund_id`, `metric` (`return`·`benchmark_return`·`aum`·`nav`), `period_kind` (`month`·`qtd`·`ytd`·`1y`·`3y`·`5y`·`itd`·`other`), `period_end` (date), `value` (Decimal; returns as fractions, 0.0123 = 1.23%), `unit` (`fraction`·`currency`·`number`), currency, `benchmark_name`, `value_as_written`, `source_page` / `source_cell`, `source_quote`, `quote_verified`, `needs_review` |
| `fact` | `document_id`, `fund_id`, key (`strategy`·`management_fee`·`performance_fee`·`liquidity`·`inception_date`·`share_class`·…), `value_text`, `source_quote` |
| `job` | `source_file_id`, `status`, `attempts`, `run_after`, `last_error` |
| `document_fts` | FTS5 over document page text + file name |

Views for the Q&A agent: `v_performance` (fund, manager, metric, period_kind,
period_end, value, benchmark_name, document name, as_of_date, observation id,
document id, only current documents), `v_facts`, `v_documents`.

## 6. Key behaviours

### 6.1 Google connection and sync
- OAuth web flow with scope `drive.readonly`, plus `openid email`. `drive.file`
  doesn't work here: it only sees files the app created or the user opened
  with it, so files other people drop into the folder would be invisible. The
  Google Cloud app stays in "Testing" mode with the user as a test user; the
  README walks through creating the client.
- Folder picker: a search box over the user's folders (`files.list`,
  `mimeType = folder`), not a pasted ID.
- On choosing a folder: store `changes.getStartPageToken` **first**, then list
  everything in the folder and queue each file. Getting the token first means a
  file added during the initial listing is caught by the next poll.
- Every 60 s (and on **Sync now**): `changes.list` from the stored token. A
  change counts if the file's `parents` include the folder. Then:
  - new file → queued;
  - `content_hash` changed → new revision queued (the old document stays until
    the new one succeeds, then flips `is_current`);
  - trashed, removed, or moved out of the folder → `deleted`, and its data is
    hidden from tables and Q&A.
- If the token is invalid (410), fall back to a full re-list of the folder and
  compare hashes. If refresh fails (revoked access), show a **Reconnect**
  banner; nothing is lost.

### 6.2 Extraction
- **Routing by type:** `application/pdf` and Google Docs (exported as PDF) →
  PDF path; `text/html`, `.eml` (`message/rfc822`) → HTML path (largest
  `text/html` part, else `text/plain`); `text/csv` and Google Sheets (first
  sheet exported as CSV) → CSV path; anything else → `unsupported`.
- **PDF path:** pdfplumber pulls each page's text (for search and quote
  checking). The PDF itself goes to Claude as a document block, so tables and
  layout get read visually and scanned pages still work. Over 50 pages →
  `unsupported` with a reason.
- **HTML path:** strip scripts and styles, keep table structure as Markdown-ish
  text, send that. It counts as "page 1".
- **Common output** (`DocumentExtraction`): doc type, manager, as-of date,
  currency, summary, and a list of funds, each with name, share class, facts,
  and observations. Each observation has `value_as_written` (e.g. `"(1.2)%"`),
  the model's normalised value, unit, period kind, period end, benchmark name,
  page, and a verbatim quote of 10–200 characters.
- **The prompt** says: extract only what is printed, never compute or infer; a
  monthly table in a factsheet gives one observation per month cell; put
  returns as fractions; use the period end date (last day of the month for
  monthly values); if a fund name matches one of the existing funds (the list
  is passed in), use that name exactly. Document content is wrapped and marked
  as data, not instructions.
- **CSV path:** a CSV can have thousands of rows, so the model doesn't read it
  row by row. Claude sees the header and the first 20 rows and returns a
  `CsvMapping`: long or wide layout; which columns are fund / date / metric /
  value / benchmark; for wide layouts, which columns are periods; the unit
  (percent, fraction, currency); date format; and a constant fund or manager if
  the file is single-fund. pandas then applies the mapping to every row. The
  source is `row N, column X`, and the quote is the raw cell text, so it is
  always verified.
- **Checks after extraction (deterministic, in code):**
  - *Value re-parse:* parse `value_as_written` ourselves (%, parentheses for
    negatives, unicode minus, `bps`, thousands separators, `m`/`bn`). If it
    disagrees with the model's value by more than 1e-9, keep **our** value and
    mark `needs_review`. Model and parser together guard against percent/decimal
    mix-ups.
  - *Quote check:* after normalising whitespace and case, the quote must appear
    in that page's text, or failing that anywhere in the document. If not →
    `quote_verified = false`. A PDF page without a text layer can't be checked,
    so it's marked unverified rather than wrong.
  - *Sanity:* a monthly return beyond ±50% or a period end after the as-of date
    → `needs_review`.
  - A file is `needs_review` if any observation is; it's still shown, with a
    marker.
- **Fund resolution:** `normalized_key` = lower-case, `&`→`and`, punctuation
  dropped, spaces collapsed, common suffixes (`fund`, `lp`, `ltd`, `limited`,
  `inc`, `plc`, `sicav`) dropped. Match the alias table; otherwise create a fund
  and alias. Share class stays a fact, not a separate fund (Claude's call: an
  allocator compares funds, and class differences mostly reflect fees). The
  Funds screen allows a manual **merge**, which moves observations and adds an
  alias so future documents land in the right place.
- **Conflicts:** the same fund + metric + period_kind + period_end from two
  current documents with different values (difference > 0.00005) is a
  *conflict*. The table shows the newest `as_of_date` value with a "2 sources
  differ" marker that opens both. Q&A is told about conflicts.
- **Failures:** API/network errors retry three times with backoff (30 s,
  2 min, 10 min), then `failed` with the error shown and a **Retry** button.
  Schema-invalid model output gets one repair retry that includes the
  validation error.
- **Idempotency:** jobs key on `(drive_file_id, content_hash)`; re-queuing the
  same revision is a no-op. **Re-extract** (manual) forces a new revision row.

### 6.3 Ask (natural-language Q&A)
- An agent loop with Claude and three tools:
  - `run_sql(query)`: one SELECT over the views. Runs on a separate read-only
    SQLite connection (`mode=ro`) with an authorizer that allows only reads of
    the views, a 2 s time limit, and a 200-row cap.
  - `search_documents(text)`: FTS5 over page text; returns document, page,
    snippet.
  - `get_schema()`: view columns, enum values, list of funds and managers,
    available period range.
- Up to 6 tool calls per question. The answer cites observation ids and/or
  document pages; the UI turns those into links that open the source document
  at the page.
- Ambiguity is answered, not asked about: "January" with no year means the most
  recent January in the data, and the answer says so. If the data can't answer,
  it says what is missing rather than guessing.
- Each answer can be expanded to show the SQL that ran and its raw rows.
- Conversation is per browser tab (not stored), with follow-ups supported.

## 7. Screens (prose; mockup deferred to the guided pass)

1. **Connect** (first run): Connect Google Drive → folder search → choose. Then
   a progress view: "14 of 20 processed".
2. **Library:** every file — name, type, manager, as-of, status chip, number of
   observations, last updated. Header: folder name, "Last synced 40 s ago",
   **Sync now**. Search box (full-text). Status filter.
3. **Document detail:** left, the source (PDF viewer via a backend proxy
   endpoint; rendered HTML in a sandboxed iframe; CSV as a table); right, what
   was extracted, grouped by fund, each value with its quote, a
   verified/unverified marker and a needs-review flag. Clicking a value jumps
   the viewer to that page. **Re-extract** button. Revision history.
4. **Performance** (default landing page once data exists): two modes.
   - *Grid:* funds as rows, months as columns, monthly returns (the
     factsheet-native view; best for "who had the best January").
   - *Rows:* every observation, all metrics and periods.
   Filters: fund, manager, metric, period kind, date range, "needs review only".
   Sortable columns, conflict and unverified markers, click-through to source,
   CSV export.
5. **Ask:** chat, with suggested questions built from the data ("Best return in
   <latest month>?", "Compare <fund> vs its benchmark YTD").
6. **Funds:** list with manager, strategy, number of documents, latest
   observation; select two → **Merge**.

## 8. Security and privacy
- OAuth tokens encrypted at rest (Fernet key from `.env`, generated on first
  run if missing). Read-only Drive scope.
- Documents are untrusted input. The extraction call has no tools that act; the
  Q&A tools are read-only by construction (read-only connection + authorizer),
  not by prompt.
- HTML is shown in a sandboxed iframe with scripts disabled.
- Document content goes to the Anthropic API; the README says so.
- Single local user, no app login: the app binds to `127.0.0.1`.

## 9. Testing and evaluation
- **Unit tests:** parsing, normalisation, fund keys, quote checks, CSV mapping,
  conflict detection, sync decisions (with a fake Drive), job state machine,
  SQL guard. The LLM sits behind an `Extractor` protocol with a fake for tests;
  no test calls the network.
- **API tests:** FastAPI TestClient against a temporary SQLite file.
- **Eval:** `evals/corpus/` holds ~15 synthetic documents from 5 fictional
  managers, made by a generator script: single- and two-column PDF factsheets,
  a scanned-style image PDF, a multi-fund statement, HTML emails with returns
  written in sentences, wide and long CSVs, mixed percent formats, a duplicate
  fund name with different punctuation, and one deliberately conflicting value.
  Each has a ground-truth JSON. `make eval` runs the real pipeline and reports
  precision/recall per metric and per file, plus the quote-verified rate. The
  README quotes the result.

## 10. Left to the builder
- Exact prompt wording (the rules in §6.2 are fixed; the phrasing isn't).
- Visual styling, beyond: dense tables, numbers right-aligned, returns shown as
  percent with two decimals, negatives in red.
- PDF viewer library (pdf.js via `react-pdf` suggested).
- Logging format.
