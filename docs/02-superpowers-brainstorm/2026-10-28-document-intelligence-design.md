# Document Intelligence Web App — Design (v2, guided brainstorm)

> **Provenance.** Built from the user's no-AI notes (`docs/01-human-brainstorm/`)
> and the guided brainstorm (`2026-10-28-brainstorm-log.md`, Q1–Q22). Each
> decision cites the question that settled it. Anything marked **(Claude's
> call)** is a gap Claude filled; it's listed again in §13 so it can be
> checked. The blind v0 (`docs/00-only-claude-ai/`) is superseded wherever
> they differ.
>
> **Status:** complete, awaiting the user's approval. Mockup:
> `2026-10-28-document-intelligence-mockup.html` (variants chosen in Q27–Q29).

## 1. Intent

An allocator's Drive folder fills up with documents from many managers:
factsheets, performance reports, emailed updates, CSV exports, and account
statements mixed in among them. Every one looks different. The app connects
to one chosen Drive folder, keeps it in sync, and turns every document into
two things:

- **Searchable documents.** Metadata, tags, and every table **as the manager
  printed it**, so a person can find what they know is in there.
- **Common rows.** Every number becomes `fund · period · measure · value`, so
  one table and one question can compare every manager.

In the user's words (Q4): *"as printed is nice to have for fund by fund
search, question level. The common rows are the insights that make the
search more than a search."*

The guiding value is from the v1 notes: **accuracy over speed**. *"Whats
more frustrating is losing confidence that the system finds something that I
KNOW is inside of a file."* Up to ~15 s for a correct answer is acceptable.

## 2. Success looks like

1. Run `docker compose up` locally (with your own OpenAI key and Google OAuth
   client), or open the CapRover deployment as an allowlisted user.
2. Sign in with Google, then pick one folder (for example the one holding
   `fixtures/`).
3. The Library fills in as files are processed: type, manager, fund, as-of
   date, tags, status. The Harborline statement is labelled `statement`; a
   scanned PDF is flagged "Scanned: no text".
4. The Data table shows common rows across all funds. Filter to monthly
   returns, January 2026, and sort: Man AHL Diversified +8.42% is top.
5. In the search box, switch to **Ask** and type "Which fund had the best
   January return?". You get the answer with a ranked table, each row linking
   to its source document.
6. In **Simple** mode, search "Terry Smith" and get the Fundsmith factsheets,
   with similar documents beneath them.
7. Drop a new factsheet into the Drive folder. Within about a minute it
   appears, gets processed, and its numbers join the table, without a click.
8. `make eval` prints precision and recall against the truth files.

## 3. Goals, non-goals, anti-goals

**Goals (MVP)**
- Google sign-in that is also the app login; allowlisted accounts only (Q11).
- One chosen Drive folder per user, top level only (Q3; top level only is
  Claude's call).
- Auto-sync by polling every 60 s, plus Sync now (Q12).
- File types: PDF, CSV, `.xlsx`, HTML, `.eml` (Q15, Q25).
- LLM extraction of metadata, printed tables and common rows, with no
  per-manager setup (brief).
- Account statements classified and extracted as account-level measures,
  kept apart from fund returns (Q21).
- Scanned or image-only PDFs detected and flagged, not extracted (Q22).
- One search box with **Simple** and **Ask** modes (Q20).
- "Needs review" and "sources differ" markers (Q19).
- Every number links to its source document (Q8).
- Similar results: same fund or manager first, then vector neighbours (Q14).
- `make eval` scored against the truth files (Q16).
- Runs locally with `docker compose up`; deployed on CapRover (Q5, Q6).

**Non-goals (MVP)**
- Roles, admin, or hiding documents from search (Q18).
- Page- or quote-level provenance (Q8: document only).
- Extracting scanned PDFs via vision (Q22).
- Google-native Docs/Sheets (Q15).
- Drive push notifications (Q12).
- An LLM judge for answers (Q16).
- A full autonomous agent: v2 (Q7, Q10).
- Dropbox and other sources: the code keeps a source interface so they can be
  added later; only Google Drive is built (v1 notes; Claude's call on the
  interface).
- Sub-folders; documents over 50 pages (Claude's call).
- Keeping copies of the original files: originals stay in Drive (Q23).
- Re-processing a file edited in place, and removing data for deleted or
  moved files (Q24).
- Caching layers, cron scale-out, BigQuery (v1 notes list them under
  Scaling: later).

**Anti-goals**
- A number shown with no way to reach the document it came from.
- Quietly picking one value when two documents disagree.
- An account's return, or a holding's unrealized gain, appearing as a fund
  return (the Harborline trap).
- Percent/decimal mix-ups (0.8% stored as 0.8).
- Q&A that changes data or invents an answer the data doesn't support.
- Anything that needs the user to configure a parser per manager.

## 4. Architecture

```
 Browser (React)  ──HTTPS──►  api (FastAPI)  ──────────►  Postgres 16 + pgvector
      ▲                         │  OpenAPI spec               ▲
      │                         │  /api/ask loop ──► LLM      │
      │                         ▼                             │
      │                     worker (same codebase)  ──────────┘
      │                       • sync poller (60 s per user)
      │                       • job runner: download → detect → extract → embed
      ▼                         │
 Google sign-in ◄──OAuth──►  Google Drive API (drive.readonly)
                                │
                           LLM provider interface ──► OpenAI (default)
```

- **Services (docker compose):** `db` (pgvector/pgvector:pg16), `api`,
  `worker`, `web`. `api` and `worker` share one Python package; the worker is
  a second entrypoint (Claude's call: no Redis or Celery; jobs live in a
  Postgres table claimed with `SELECT … FOR UPDATE SKIP LOCKED`).
- **Stack (Q5):** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, Postgres 16 +
  pgvector, React + TypeScript + Vite, Tailwind CSS + shadcn/ui (Q26),
  TanStack Query and Table.
- **LLM provider (Q9):** one interface, `LLMProvider`, with three operations:
  structured extraction (file in, schema-validated JSON out), tool-calling
  chat, and embeddings. `OpenAIProvider` is the only implementation and the
  default. Model names come from config. Exact default model ids are fixed
  during the spike against OpenAI's current docs, not guessed here.
- **Deployment (Q6, Q32):** the user's existing CapRover server. The build
  ships the CapRover config (`captain-definition` per app) and a deploy
  section in the README; deploying and a smoke test against the live URL
  happen together with the user as the last step. CapRover, with one app each for `api`, `worker` and
  `web`, and Postgres with pgvector as a CapRover app (Claude's call on the
  layout). Runs on the user's OpenAI key. Local runs use the reviewer's own
  key and Google OAuth client.

## 5. Sign-in, users and Drive access

- **Google OAuth web flow** with scopes `openid email profile
  https://www.googleapis.com/auth/drive.readonly`. One sign-in both logs the
  user in and grants Drive access (Q11). `drive.readonly` is needed because
  `drive.file` can't see files other people drop into the folder.
- **Allowlist:** `ALLOWED_EMAILS` (comma-separated) in config. Anyone else
  gets a "not on the list" page and nothing is stored.
- **Google app status (Q30):** the OAuth app is published to Production
  without verification, so refresh tokens don't expire after 7 days as they
  do in Testing mode. Users see Google's "unverified app" warning once. The
  spike confirms Google allows this with `drive.readonly`; if it doesn't, fall
  back to Testing mode plus a Reconnect banner. The README explains the
  setup.
- **Session:** a signed, HTTP-only cookie. Google refresh tokens are stored
  Fernet-encrypted (Claude's call).
- **Isolation:** every row (folder, file, document, table, common row, chunk,
  job) carries `user_id`. Every query is scoped by it, including the Ask
  tools, which run as the asking user.
- **Revoked access:** a failed token refresh sets `needs_reconnect`; the UI
  shows Reconnect; nothing is deleted.

## 6. Sync

- **Picking the folder:** a searchable list of the user's Drive folders. The
  user picks one and can change it later; changing it clears that user's data
  after a confirmation (Claude's call).
- **Order on selection:** save `changes.getStartPageToken` **first**, then
  list the folder and queue every supported file. A file added during the
  listing is then caught by the next poll.
- **Every 60 s per user, and on Sync now:** `changes.list` from the token. A
  change counts if the file's `parents` include the folder.
  - New file → queued.
  - A file is processed once. An edit in place is ignored and the first
    result is kept; a manual **Re-extract** button covers the rare case
    (Q24).
  - Trashed, removed, or moved out of the folder → ignored in the MVP. Its
    data stays, and the viewer shows "No longer in Drive" if opened (Q24).
- **Expired change token (410):** re-list the folder and queue any file not
  seen before.
- **Unsupported types:** listed in the Library as "Unsupported", not
  processed.
- **Source interface (Claude's call):** `DocumentSource` with
  `list_folder`, `poll_changes`, `download`. Google Drive is the one
  implementation, which keeps the v1 notes' "modular enough for drop box"
  open without building it.

## 7. Processing pipeline

Each job: **download → detect → extract → check → store → embed**.

### 7.1 Detect
- Route by MIME type or extension: PDF, CSV, `.xlsx`, HTML, `.eml`
  (largest `text/html` part, else `text/plain`). Anything else →
  `unsupported`.
- **Scanned check (Q22):** extract the text layer per page with pdfplumber.
  If more than half the pages have fewer than 20 characters of text, mark the
  file `scanned_no_text` and stop: no LLM call (thresholds are Claude's call).
- PDFs over 50 pages → `unsupported`, with the reason shown.

### 7.2 Extract (LLM, through `LLMProvider`)
One structured-output call per document returns:
- **Metadata, fixed fields** (Q13, Q17): `doc_type` (`factsheet` ·
  `performance_report` · `statement` · `investor_letter` · `other`),
  `manager`, `funds[]` (name, share class), `as_of_date`, `currency`, a
  one-line `summary`.
- **Free tags:** 3–8 short tags (for example `global equity`, `trend
  following`, `UCITS`). They feed search and appear as "tags" under results
  and files; there's no filter for them in the UI (Q17).
- **Printed tables:** every table, with title, header rows and body rows as
  the text strings printed, in order (Q4).
- **Common rows:** `entity` (fund or account), `entity_kind` (`fund` ·
  `account`), `share_class` (null when the document gives none), `measure` (`return` · `benchmark_return` · `aum` · `nav` ·
  `account_value` · `account_return`), `period_kind` (`month` · `qtd` ·
  `ytd` · `1y` · `3y` · `5y` · `itd` · `calendar_year` · `other`),
  `period_end`, `value_as_written`, `value`, `unit`, `currency`,
  `benchmark_name`, and a pointer to the printed table cell it came from
  (`table_index`, `row`, `col`) when it came from a table.
- **Prompt rules:** extract only what is printed and never compute; net, not
  gross, is the return; exposures, unrealized gains, "best month" statistics
  and bps-over-hurdle figures are not returns; a statement's performance is
  the account's (`entity_kind = account`); period end is the last day of the
  period; reuse a fund name from the user's existing funds when it matches.
  Document text is wrapped and marked as data, not instructions.
- **How the file is sent:** PDFs go to the model as files, so layout and
  tables are read visually; HTML/.eml as cleaned text with table structure
  kept.
- **CSVs and `.xlsx` (Q25):** each `.xlsx` sheet is read with pandas
  (openpyxl) and handled exactly like a CSV. The model sees the header and the first 20 rows and returns a
  column mapping (long or wide layout; which columns are entity, date,
  measure, value; unit; header and footer rows to skip). pandas applies the
  mapping to every row. The printed table is the CSV itself (Claude's call:
  this keeps large CSVs like TSP fast and exact).

### 7.3 Check (deterministic code)
- **Value re-parse:** parse `value_as_written` (%, parentheses, U+2212
  minus, `bps`, `m`/`bn`, thousands separators). If it disagrees with the
  model's `value`, keep the parsed value and mark the row `needs_review`.
- **Sanity:** a monthly return beyond ±50%, or a period end after the as-of
  date → `needs_review`.
- **Fund identity:** normalise names (case, punctuation, `&`, suffixes like
  `LP`, `Ltd`, `Fund`) and match an alias table, so `Northwind Global Macro
  Fund, L.P.` and `…Fund LP` are one fund. Share class stays an attribute.
- **Sources differ:** same user, entity, share class, measure, period kind
  and period end across two current documents, with values differing by more than 0.00005 →
  both rows marked; the table shows the newest as-of value with a "sources
  differ" marker that opens both (Q19).
- A file with any `needs_review` row shows "Needs review" in the Library and
  is still displayed.

### 7.4 Store and embed
- **Originals are not stored (Q23).** The app keeps the Drive file id and
  path. The in-app viewer streams the file from Drive through
  `GET /api/files/{id}/content` with the user's token when it is opened.
  Retry, Re-extract and `make eval` download again.
- Store what is derived: the document record (metadata, tags, summary,
  extracted page text), printed tables, common rows and chunks.
- **Chunks for search:** page text in pieces of roughly 800 tokens, each
  printed table rendered as text, and a metadata card (manager, funds, type,
  date, tags, summary). Each is embedded through `LLMProvider.embed` (OpenAI
  embeddings, Q6) into pgvector, and indexed for Postgres full-text search.
- **Failures:** API errors retry 3 times with backoff (30 s, 2 min, 10 min),
  then `failed` with the error and a Retry button. Invalid structured output
  gets one repair attempt.

## 8. Screens

Five surfaces (Q20), all scoped to the signed-in user:

1. **Connect:** sign in, pick a folder, sync progress.
2. **Library:** every file with status (`queued` · `processing` · `done` ·
   `needs review` · `failed` · `unsupported` · `scanned: no text`), type,
   manager, fund, as-of, tags, last synced, Sync now.
3. **Document view:** the file rendered in the app (PDF viewer; sandboxed
   HTML; CSV as a table) beside its printed tables and its common rows.
4. **Data table:** common rows across all funds and accounts; filters for
   fund, manager, measure, period kind and date range; needs-review and
   sources-differ markers; each row links to its document; CSV export.
5. **Unified search** with a mode toggle:
   - **Simple:** hybrid full-text + vector search over chunks. Results show
     document, path, metadata, tags and a snippet, with **Similar** beneath:
     same fund or manager first, then nearest documents by embedding (Q14).
   - **Ask:** the question goes to the Q&A loop (§9). The answer is text,
     optionally a data table, with links to source documents.

**Layout** (`2026-10-28-document-intelligence-mockup.html`):
- **Search results: variant A (Q27).** The search box sits in the header on
  every screen and opens its own results page with a URL, so Back returns to
  an answer after opening a source document. Ask answers need the width for
  ranked tables.
- **Document view: variant A (Q28).** The file on the left, streamed from
  Drive; on the right, tabs for "As printed" (a picker per table or sheet)
  and "Common rows". Man AHL alone has 6 tables and 158 rows, which is too
  long to stack.
- **Data table: variant A (Q29).** One row per number: fund or account ·
  share class · period · measure · value · markers · source document. When
  sources differ, both rows stay visible. A funds × months grid may come
  later as a second view.
- **UI kit (Q26):** Tailwind + shadcn/ui. The mockup's components (Button,
  Badge, Tabs, ToggleGroup, DataTable with faceted filters, Alert, Progress,
  Skeleton, Tooltip, Popover + Command) are the build's components.

## 9. Ask: questions over the app's own APIs

- **Tools are the app's own endpoints (Q7).** The read endpoints that Ask may
  use carry an OpenAPI tag (`ask`). At startup the server turns the OpenAPI
  operations with that tag into tool definitions for the model: name,
  description, parameter schema. The same endpoints serve the UI, so "agent
  tools as APIs first" holds, and a v2 agent can reuse them unchanged.
- **Endpoints tagged `ask` (initial set):** search documents, list funds and
  managers, query common rows (filters, sort, limit), get a document's
  metadata and tables, list measures and the available date range.
- **Loop (Q10):** the model may call up to 5 tools per question. The server
  runs each as an in-process request **as the asking user**, GET only, and
  returns the JSON. Then the model answers.
- **Answer shape:** text, an optional table (columns + rows), and the source
  documents cited. Each cited document id is checked against the user's
  documents, and unknown ids are dropped.
- **Rules given to the model:** January with no year means the latest January
  in the data, and the answer says so. Mention sources-differ conflicts. If
  the data can't answer, say what's missing.
- **Time budget:** about 15 s (v1 notes). Show progress ("Querying common
  rows…") while it runs.

## 10. Data model (sketch)

`user` (email, encrypted Google token, needs_reconnect) · `watched_folder`
(user, Drive folder id/name, change token, last synced) · `source_file`
(user, Drive file id, path, name, mime, status, error) · `document` (file,
doc_type, manager, as_of, currency, summary, tags[],
model, prompt_version) · `fund` + `fund_alias` (per user) · `printed_table`
(document, index, title, header JSON, rows JSON) · `common_row` (document,
fund or account, entity_kind, measure, period_kind, period_end, value,
share_class, value_as_written, unit, currency, benchmark_name,
table_index/row/col,
needs_review) · `chunk` (document, kind, text, tsvector, embedding vector) ·
`job` (file, status, attempts, run_after, last_error).

## 11. Testing

- **Unit:** value parsing, fund normalisation, scanned detection, CSV mapping,
  sources-differ, sync decisions (fake source), job states, the Ask tool
  builder and its user scoping. LLM calls replay recorded responses; unit
  tests never hit the network.
- **Integration (v1 notes: "lean here with Docker"):** pytest against a real
  Postgres + pgvector container. Covers the pipeline end to end with recorded
  LLM responses, API filters and isolation between two users.
- **Eval (Q16, Q31):** `make eval` runs the real provider over `fixtures/`
  and scores against the `.truth.json` files, reporting precision and recall
  per document and per measure. It's a report with no pass mark. Recall uses
  every truth file; precision only those not marked `partial`. A row matches
  on normalised entity, share class, measure, period kind and period end,
  with value tolerance 0.00005. It also checks that the Harborline traps don't
  leak into fund returns.
- **E2E:** deferred (v1 notes: "if time permits").

## 12. Security

- Read-only Drive scope. Allowlisted sign-in. Encrypted refresh tokens.
  Per-user scoping on every query.
- Ask tools are GET-only and run as the user. The model never sees SQL or
  other users' data.
- Document content is untrusted. HTML is shown in a sandboxed iframe with
  scripts off.
- Documents go to OpenAI; the README says so.

## 13. Claude's calls (please check)

1. No Redis/Celery: Postgres job table + worker entrypoint.
2. Top-level folder only; 50-page cap. (`.xlsx` was excluded here; the user
   brought it back in, Q25.)
3. Changing the folder clears that user's data, after a confirmation.
   (Re-extract is a manual button; edits in place are otherwise ignored, Q24.)
4. Scanned threshold: more than half the pages under 20 characters of text.
5. CSVs: LLM maps columns once and pandas applies the mapping.
6. `DocumentSource` interface kept for future Dropbox, Drive only built.
7. CapRover layout: separate api, worker and web apps, plus a pgvector
   Postgres app.
8. Refresh tokens Fernet-encrypted; signed session cookie.
9. Share class is an attribute of a fund, not a separate fund, but it is part
   of each common row's identity: Alderbank A EUR (+3.12%) and I EUR (+3.21%)
   are two series, never merged and never flagged as "sources differ"
   (builder check).
10. Default OpenAI model ids decided in the spike from current docs.
11. **Re-extract** replaces that document's tables, common rows and chunks
    (no history kept). It is disabled when the file is no longer in Drive; the
    app learns that when the viewer's stream from Drive fails.
12. Two documents that agree on the same fund, share class, measure and
    period give two common rows, both shown in the Data table with their
    sources. No marker, since they agree; Ask counts the value once.

## 14. Open

- Anything the builder check raises that only the user can answer.
