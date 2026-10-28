# Spike findings — Document Intelligence v2

Date: 2026-10-28. Spec: `docs/02-superpowers-brainstorm/2026-10-28-document-intelligence-design.md`.
Throwaway code lives in the session scratchpad
`/private/tmp/claude-501/-Users-ibrown-Code-claude-ai-equi-takehome/5f593e56-6a9a-478d-ba06-926e7e685e8f/scratchpad/spike/`
(not in the repo; the Drive probe is reproduced in full at the end of this file).

## 0. Headline

| Item | Result |
|---|---|
| **A. Live extraction runs (5 docs, real model)** | **NOT RUN. The `OPENAI_API_KEY` in the environment is rejected by OpenAI: `401 invalid_api_key` on `GET /v1/models`.** No latency, token, cost or accuracy numbers exist yet. Everything under A that does not need the model was run (schema, scoring, CSV/xlsx path, email cleaning, size estimates). The runner is ready: one command once the key is fixed (section A.7). |
| B. Scanned detection | RUN. Rule flags only the image-only PDFs. |
| C. Google OAuth + Drive | Docs-researched; **cannot be run without an OAuth client**. Unverified Production + `drive.readonly` is allowed in practice per Google's own cap wording, with a 100-user lifetime cap. Probe script written and compiles; the user must run it. |
| D. Platform | RUN: pgvector + SQLAlchemy works; FastAPI in-process GET tools + OpenAPI-to-tool conversion works. CapRover is from docs only. |

Spec amendments are collected in section E. The user-only steps are in section F.

---

## A. Extraction

### A.1 API and model ids (from current OpenAI docs, fetched today)
Sources: developers.openai.com/api/docs/models, /pricing, /guides/structured-outputs, /guides/pdf-files, /guides/embeddings.

- **API: Responses API.** Structured output = `text={"format": {"type":"json_schema","name":..., "strict":True,"schema":...}}`. PDF = an `input_file` item with `file_data: "data:application/pdf;base64,..."` (or `file_id` uploaded with purpose `user_data`). Chat Completions also accepts PDFs (`file` part) but has no `detail` control; use Responses.
- PDF handling (docs): for vision-capable models the API sends **both extracted text and page images**. `detail` (`auto|low|high`) affects only the images; `auto` means `high` on GPT-5.6 and later. Limit: under 50 MB per file and 50 MB combined per request; no page limit is stated (the spec's 50-page cap is our own rule).
- Current text models (docs table; 1.05M context, 128K max output):

| Model id | Input / output per 1M tokens |
|---|---|
| `gpt-6-astra` | $10 / $50 |
| `gpt-6.1-sol` | $2 / $10 |
| `gpt-6.1-terra` | $1 / $5 |
| `gpt-6-luna` | $0.10 / $0.50 |

- Embeddings: `text-embedding-3-small` (1536 dims, $0.02/M), `text-embedding-3-large` (3072 dims, $0.13/M). Both accept a `dimensions` parameter; max 8192 input tokens.
- **Not verified live:** that `gpt-6.1-sol` accepts PDF `input_file` plus strict `json_schema` together. The docs say structured outputs work on the latest models and PDF parsing needs a vision-capable model, but the key was rejected, so this is unconfirmed. First thing to run once the key works: `client.models.list()` to confirm the ids exist for this account.

**Decision (proposed defaults, to be confirmed by the first live run):**

| Config | Default | Why |
|---|---|---|
| `EXTRACT_MODEL` | `gpt-6.1-sol` | Accuracy over speed (spec §1); a quarter of Astra's price. Fall back to `gpt-6-astra` only if the eval shows the trap rows leak. |
| `ASK_MODEL` | `gpt-6.1-terra` | Tool loop has a 15 s budget; cheaper and faster. |
| `MAPPING_MODEL` | `gpt-6.1-terra` | CSV column mapping is a small task. |
| `EMBED_MODEL` | `text-embedding-3-small`, **1536 dims** | See D.1: pgvector HNSW cannot index above 2000 dims, so 3072-dim `3-large` is unindexable unless truncated with `dimensions=1536`. Small at $0.02/M is plenty for ~800-token chunks. |

### A.2 Strict-mode limits (docs) vs our schema (run)
Docs limits: root must be an object (no root `anyOf`); every property in `required`; `additionalProperties:false` on every object; optional = `["type","null"]`; max 5,000 properties total, 10 levels deep, 120,000 chars of names/enums, 1,000 enum values; `allOf/not/if/then/else/dependent*` unsupported; `minItems/maxItems/pattern/format/min/max` supported on non-fine-tuned models; key order in the output follows schema order.

Run (`schema.py` + `strict.py`; the Pydantic model converted with the OpenAI SDK's own strict converter, then checked):
```
Extraction props 28 objdepth 2 bad [] chars 3177
CsvMapping props 16 objdepth 2 bad [] chars 2064
```
The §7.2 schema (metadata, funds, tags, printed tables, common rows with `entity_kind`, `share_class`, table cell pointer) is about 28 properties: nowhere near any limit. **Caveat:** this validated the schema against the documented rules locally; the API itself was not called, so a server-side rejection is not ruled out.

Schema design notes that matter:
- Every field the model might not have must be `Optional[...]` and still appears in `required` (null, not absent). Done in `schema.py`.
- `period_end` as a plain `YYYY-MM-DD` string (the `format: date` keyword is allowed but adds nothing; the re-parse in §7.3 validates).
- Printed tables as `list[list[str]]` is fine for strict mode.

### A.3 Output size is the real risk (estimated, not measured)
Run (`est.py`, tiktoken `o200k_base`):
```
man-ahl: text layer 6,935 tokens over 8 pages; ~233 "x.xx%" figures; one serialised common row = 108 tokens
fundsmith 01: text layer 5,869 tokens over 4 pages; 28 "x.xx%" figures
```
Man AHL carries the 2016-2026 monthly grid (~140 monthly cells) plus the share-class and fee tables. At ~108 tokens per common row, the rows alone are ~15k output tokens, plus the printed tables (spec: 6 tables, 158 rows) at roughly 6-8k: **an estimated 20-25k output tokens for Man AHL.** At typical generation speed that is minutes, not seconds, and the cost is dominated by output ($10/M: about $0.20-0.25 per Man AHL document on `gpt-6.1-sol`). Input is small: ~7k text tokens plus page images. This is a back-of-envelope estimate; replace it with the measured numbers from the first live run.

Consequences:
1. Set `max_output_tokens` high (the model allows 128K) and a long client timeout (SDK default is 10 min); consider streaming. Spec §7.4 retry/backoff (30 s, 2 min, 10 min) must not treat a slow call as a failure.
2. A truncated response (`status == "incomplete"`, reason `max_output_tokens`) is invalid JSON, so it must be handled before the "one repair attempt" in §7.4.
3. Shrink the row shape. Proposal: rows reference `funds[]` by `fund_index` (int) instead of repeating `entity`, `share_class`, `currency`, `benchmark_name` strings, and drop the model-written `value` entirely: §7.3 already re-parses `value_as_written` and keeps the parsed value, so the model's copy is redundant. Estimated 108 down to ~50 tokens per row.
4. Alternative if it is still too slow: two calls (metadata+tables, then rows). Not recommended before measuring.

### A.4 Scorer
`score.py` implements the §11 matching rule: normalised entity (case, punctuation, `&`, `LP/Ltd/LLC/Fund`, parenthesised ids stripped), share class, measure, period kind, period end; value tolerance 0.00005. Used on the CSV path below (35/35 and 28/29) so it is validated against real truth files. Truth files use the keys `fund/share_class/metric/...`; the model output uses `entity/measure/...`; the scorer maps between them.

### A.5 CSV column mapping (§7.2) — RUN with a hand-written mapping (stand-in for the model)
`csvmap.py` applies a `CsvMapping` with pandas (UTF-8 BOM, CRLF, `(0.84%)`, U+2212, `n/a`, preamble and footnote rows all handled) and scores against the truth files:

| File | Truth rows | Matched | Notes |
|---|---|---|---|
| northwind (long layout) | 35 | **35 / 35**, 0 extra | `2.37` under `Net Return %` becomes 0.0237; the `Global Macro Fund LP` July alias matches; blank May is dropped. |
| alderbank (wide layout) | 29 | **28 / 29**, 1 extra | Miss: Asia Income YTD. Truth says period end 2026-08-31 (asterisk footnote); the mapping said 2026-09-30. |

What this proves: the approach works and is exact. What it exposes (spec amendment E4): a column-level mapping cannot carry a **footnote-driven per-entity period end**, and the model only sees "the header and the first 20 rows", which for a long CSV never includes the footnotes at the bottom. The mapping schema in `schema.py` (`CsvMapping`/`ValueCol`) needs: per-column `measure`, `period_kind`, `unit` (`percent_number | percent_string | fraction | currency`), an optional `benchmark_name_column`, and a list of per-entity `period_end` overrides; and the model needs the last ~5 rows too.

`.xlsx` (`xl.py`): I built a real xlsx from the Northwind CSV (true dates, numeric cells) with pandas and read it back with `read_excel(sheet_name=None, dtype=str)`. Dates arrive as `2026-01-31 00:00:00` and numbers as `1.1`; writing each sheet to CSV text and sending it through the same code path scored **35/35**. Caveats not tested: percent-formatted cells come back as fractions (0.0237, so the mapping unit must be `fraction`), merged cells, formulas without cached values, and hidden sheets.

### A.6 Email text (§7.2 "cleaned text with table structure kept") — RUN
`run_extract.py:eml_text()`. Findings:
- Kestrel (HTML + plain): the HTML part is chosen and its table becomes `| Period | Fund (net) | MSCI World |` rows: good. Only one part is sent, which satisfies the "extract once" trap.
- Larchmont (HTML-only, nested template tables): a naive "each `<table>` becomes pipe rows" duplicated all the text (outer layout table rows contain the inner tables). Fix used: process innermost tables first, and unwrap any table that contains another table. After the fix the quarterly grid comes out as clean rows (`| Multi-Strategy | −0.60% | 1.15% | ...`, `| Relative Value | – | – | ...`). One residual: single-cell wrapper tables still render as one-cell pipe rows; harmless.
- U+2212 minus and en-dash `–` placeholders are preserved, which §7.3's parser must handle (it already lists U+2212; add the en-dash/em-dash as "no value").

### A.7 What still has to be run (needs a valid key)
```
cd /private/tmp/claude-501/-Users-ibrown-Code-claude-ai-equi-takehome/5f593e56-6a9a-478d-ba06-926e7e685e8f/scratchpad/spike
export OPENAI_API_KEY=<a working key>          # the current one returns 401
uv run --no-project --with openai --with pydantic --with beautifulsoup4 --with pdfplumber --with tiktoken \
   python run_extract.py --model gpt-6.1-sol
```
It sends the 5 documents (Man AHL, Fundsmith Jan, UVic, Harborline as PDFs; Kestrel as cleaned text), prints per document: seconds, input/output tokens, dollars, status, number of tables and rows, recall hits against truth, missing rows, wrong values, and writes the raw JSON to `out/`. `--dry` builds the requests without calling. After the run, read `out/*.json` against each truth file's `traps` list (Man AHL `n/a` cells, UVic 2025 page dated 2025, Fundsmith comparators and "Best Month", Harborline G/L % and `account` kind, Kestrel gross vs net and exposure). Expected spend: roughly $0.3-0.6 total on `gpt-6.1-sol`. Run the Alderbank/Northwind mapping step with the model by sending `CsvMapping.schema.json` the same way.

**Open until then:** which model/latency/cost, whether printed tables come back faithfully, whether each trap is avoided, and the actual strict-mode acceptance of the schema.

---

## B. Scanned detection (§7.1) — RUN
`scan.py`: pdfplumber `extract_text()` per page, rule "more than half the pages under 20 characters". I generated an image-only PDF with Pillow (30 lines of text drawn into a raster, 1 page and a 3-page copy).

| File | Pages | Chars per page | Flagged |
|---|---|---|---|
| blackrock-ishares_factsheet_swda_2026-09 | 4 | 2198, 1445, 1152, 5320 | no |
| fundsmith_factsheet_2026-01 | 4 | 6396, 2674, 6865, 4891 | no |
| fundsmith_factsheet_2026-08 | 4 | 6488, 2671, 6804, 4891 | no |
| jpmorgan_factsheet_jpef_2026-09 | 2 | 5620, 9049 | no |
| man-ahl_factsheet_2026-08 | 8 | 2752, 1792, 1100, 2187, 4216, 7458, 8109, 1685 | no |
| uvic-pension_performance-report_2026-07 | 2 | 584, 730 | no |
| harborline-custody_account-statement_2026-09 | 3 | 657, 537, 250 | no |
| generated image-only (1 page) | 1 | 0 | **yes** |
| generated image-only (3 pages) | 3 | 0, 0, 0 | **yes** |

Rule confirmed on the fixtures (smallest real page: 250 chars; so 20 has a wide margin). Not covered: a scan that already has an OCR text layer (would pass as text, which is fine), and a mixed document with a scanned cover but text body (passes, also fine). pdfplumber prints `Could not get FontBBox...` warnings on some fixtures; harmless, suppress logging. Real-PDF table detection by pdfplumber is irrelevant here (tables are read visually by the model).

---

## C. Google OAuth and Drive (docs only; no credentials were available)

### C.1 Unverified Production app with restricted `drive.readonly`
Sources: Google Cloud Help "Manage App Audience" (support.google.com/cloud/answer/15549945) and "unverified apps" (answer/7454865); Drive scopes page (developers.google.com/workspace/drive/api/guides/api-specific-auth); OAuth 2.0 overview (refresh token expiry).

- `drive.readonly` is **restricted** (also `drive`, `drive.metadata.readonly`). `drive.file` is non-sensitive but only sees files the app created or the user opened with it, so the spec's reason for `drive.readonly` (files other people drop in) holds.
- Google never states "unverified Production apps may use restricted scopes" in one sentence. What the docs do say: In-production apps are open to any Google account; when the request includes scopes "that haven't been approved", Google shows the **Unverified app** screen; the user cap "limits the number of users that can grant permission to your app when requesting unapproved sensitive or restricted scopes": **100 new users in total, after the app presents the unverified app screen, over the entire lifetime of the project, and it cannot be reset**. A cap on grants is only meaningful if grants are possible, so the request is allowed. This matches common practice but **has not been run here** (no client). The probe script (section G) is what confirms it; the first sign-in with your own client is the test.
- **What users see:** "Google hasn't verified this app" warning before the consent screen; the user continues via Advanced then "Go to <app> (unsafe)". (The step names are from experience; the fetched help pages did not quote them.) Then the normal consent listing Drive read access.
- **User cap:** 100 lifetime, counted per project when the warning screen is shown. Reviewers who run `docker compose up` with their own OAuth client use their own project and their own 100. For the CapRover deployment, `ALLOWED_EMAILS` should be kept far under 100.
- **Refresh-token lifetime:**
  - Testing status: "Authorizations by a test user will expire seven days from the time of consent", and the offline refresh token expires too. **Confirmed in docs.** The exception is a client requesting only `openid/email/profile`; ours adds `drive.readonly`, so it applies. Up to 100 test users.
  - Production (including unverified): no 7-day rule. Remaining ways a token dies: unused for 6 months; user revokes; more than 100 refresh tokens for one account and client (oldest dies silently); admin policy (`admin_policy_enforced`); a Workspace session-length control (`invalid_grant`, `error_subtype=invalid_rapt`). The §5 "failed refresh sets needs_reconnect" handling covers all of them.
- Verification would need a security assessment for restricted scopes that are stored on servers. Not needed for unverified operation, so it is out of scope, but the README should say that a public launch would need it.
- Production requirements to note in the README: web client redirect URIs must be HTTPS except `http://localhost`; the 100-user cap and warning screen apply; changing redirect URIs on the client can take several minutes to apply.
- Caveat: Google also asks Production apps for brand info (app name, support email, privacy-policy and home-page URLs on a domain you own). Whether an unverified app can skip the privacy-policy URL on a personal project is not stated; if the consent screen refuses to publish without it, a one-page policy on the CapRover domain is enough.

**Decision:** the spec's Q30 plan stands (Production, unverified). Keep the Testing-mode fallback with the Reconnect banner (it is the documented behaviour at 7 days).

### C.2 Auth request
`access_type=offline` and `prompt=consent` are both needed to get a refresh token reliably: Google returns a refresh token only on the first consent unless `prompt=consent` is sent. One request with `scope=openid email profile https://www.googleapis.com/auth/drive.readonly` yields one consent screen, and the token response carries an `id_token` (email/sub for login) plus the Drive access token. Use `OAUTHLIB_RELAX_TOKEN_SCOPE` (or compare scope sets) because Google returns `email` as `https://www.googleapis.com/auth/userinfo.email` and may reorder. Persist the refresh token only when present in the response (later logins without `prompt=consent` would not include one; the app should always send `prompt=consent` or keep the old token if none comes back). Validate `state`.

### C.3 Drive calls
- `changes.getStartPageToken` then `changes.list`: `pageToken`, `pageSize` up to 1000 (default 100), `includeRemoved`, `supportsAllDrives`, `includeItemsFromAllDrives`, `restrictToMyDrive`, `spaces`. The response has `nextPageToken` while paging and `newStartPageToken` at the end; both do not expire (but the spec's 410 handling stays for tokens that become invalid). **A `fields` mask is required to get `parents`/`md5Checksum`/etc.** and it works on the `file` sub-object: `changes(changeType,fileId,removed,time,file(id,name,mimeType,md5Checksum,trashed,parents)),nextPageToken,newStartPageToken`. Whether `parents` is populated for items shared into a folder the user does not own (file visible, parent not) could not be checked without credentials: **the probe prints it; confirm with a file someone else dropped in the folder**.
- `changes.list` returns every change anywhere in the user's accessible Drive, not just the chosen folder, so filtering by `parents` is client-side (as the spec says). A removed item (`removed=true`) has no `file`; spec's "removed, trashed or moved out: ignored" matches. Do not set `restrictToMyDrive` (it omits shared files not added to My Drive).
- `files.list` for one folder: `q="'<id>' in parents and trashed=false"`, `pageSize` up to 1000, loop on `nextPageToken`, `supportsAllDrives=true`, `includeItemsFromAllDrives=true`, `fields=nextPageToken,files(id,name,mimeType,md5Checksum,size,modifiedTime,parents,trashed)`.
- `files.get?alt=media` streams the raw bytes (use `stream=True` and proxy chunks to the browser). Google-native types (Docs/Sheets) fail with 403 on `alt=media`: consistent with the non-goal; list them as Unsupported by `mimeType` prefix `application/vnd.google-apps.`.
- **Quota:** Drive usage limits: 1,000,000 units/min/project and 325,000 units/min/user/project; list-type calls cost about 100 units (docs; `changes.list` is not in the cost table, taken as list-type). Polling every 60 s is ~1,440 calls/day/user = 144,000 units a day: negligible. Quota breaches return 403 `userRateLimitExceeded` or 429; back off exponentially (docs: `min(2^n + random_ms, 32-64 s)`). The worker should treat 403/429 as "retry later" and not as `needs_reconnect`; only `invalid_grant` is the reconnect case.

### C.4 Google Cloud console steps to create the client
Console label names change; these are the "Google Auth Platform" pages as of this writing.
1. console.cloud.google.com, create or choose a project (use a dedicated one for the CapRover deployment).
2. APIs & Services, Library, search "Google Drive API", Enable.
3. Google Auth Platform (or "OAuth consent screen"), Get started: app name, support email; Audience **External**; contact email; accept policy.
4. Data Access (Scopes), Add or remove scopes: tick `openid`, `.../auth/userinfo.email`, `.../auth/userinfo.profile`; add `https://www.googleapis.com/auth/drive.readonly` (manually add it if it is not listed). Save.
5. Clients, Create client, type **Web application**, name e.g. `doc-intel-local`.
   Authorized redirect URIs (exact, no trailing slash differences):
   - Probe script: `http://localhost:8000/auth/callback`
   - Local app (route to be named in the plan; proposed): `http://localhost:8000/api/auth/google/callback`
   - CapRover app: `https://<api-app>.<your-caprover-root-domain>/api/auth/google/callback`
   Authorized JavaScript origins can stay empty (server-side flow). Create, copy the client ID and secret into your env, never into the repo.
6. Audience: while in **Testing**, add each Google account that will sign in under Test users (max 100; tokens last 7 days). To follow the spec (Q30), click **Publish app** to move to **In production**; expect the "unverified" warning and the 100-new-user lifetime cap.
7. Redirect URI edits can take a few minutes to take effect.

---

## D. Platform checks

### D.1 pgvector — RUN
Image `pgvector/pgvector:pg16` pulled and started (`PostgreSQL 16.15`, extension `vector 0.8.7`), container since removed. `pgv.py` with SQLAlchemy 2 + `pgvector.sqlalchemy.Vector` (psycopg 3):
- `Vector(1536)` column + `Index(..., postgresql_using="hnsw", postgresql_ops={"emb":"vector_cosine_ops"}, postgresql_with={"m":16,"ef_construction":64})` creates cleanly; GIN index on a `TSVECTOR` column too.
- Cosine query `select(Chunk.id, Chunk.emb.cosine_distance(q).label("d")).where(Chunk.user_id == 1).order_by(d).limit(3)` returned ranked rows scoped to the user (distances 0.93-0.95 for random vectors, as expected).
- Full-text: `Chunk.tsv.op("@@")(func.websearch_to_tsquery("english","terry smith"))` found the seeded "Terry Smith" chunk.
- **`vector(3072)` with an HNSW index fails: `column cannot have more than 2000 dimensions for hnsw index`.** Hence 1536 dims (A.1).
- Alembic note for the plan: the migration must `CREATE EXTENSION IF NOT EXISTS vector` before creating the column, and the `pgvector.sqlalchemy.Vector` type must be imported in the migration.

### D.2 Ask tools as in-process GET calls — RUN
`tools.py`: a FastAPI app with routes tagged `ask` (query rows, get document) plus an `admin` POST and an untagged GET. Converted `app.openapi()` into OpenAI function tools and called them through `httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://app")`.
- Only `GET` operations whose `tags` include `ask` became tools (2 of 4 routes); the POST and the untagged GET were excluded.
- Tool name = `operationId` (set it explicitly with `operation_id=`; the auto id is ugly). Path parameters are substituted into the URL; the rest are query params.
- Optional params appear as `anyOf [type, null]` in OpenAPI 3.1; they are not strict-mode compatible (strict needs every property required and no defaults), so emit the tools with `"strict": false`. Fine for tool calls.
- **Gotcha:** FastAPI's `summary` is auto-generated from the function name ("Doc"); I took `description or summary` and the tool got the description "Doc". Require a docstring on every `ask` route and fail startup if one is missing. Parameter `description=` strings (`Query(..., description=...)`) do carry through to the tool schema.
- Auth: the in-process request ran as the asking user via a header consumed by the same `Depends(user)` the browser path uses (test used an `x-user` header; the real one should be a server-minted internal token, not the browser's cookie, and the header must not be a model-visible parameter: the converter skips it).
- `ASGITransport` does not run lifespan events; tests need the app's dependencies available without startup hooks, or construct the app per test.

### D.3 CapRover (docs; not run — there is no CapRover server access here)
- `captain-definition` is JSON at the project root with `"schemaVersion": 2` and either `templateId`, `dockerfilePath`, inline `dockerfileLines`, or `imageName`. The docs support **several definition files in a monorepo** (e.g. `captain-definition-api`) and a per-app "Captain Definition Path" in the app's Deployment tab; `COPY` paths stay relative to the repo root.
- Plan: `captain-definition-api`, `captain-definition-worker`, `captain-definition-web`, each `{"schemaVersion": 2, "dockerfilePath": "./deploy/Dockerfile.api"}` (and `.worker`, `.web`). Three CapRover apps. Set the api app's container HTTP port (8000) and enable HTTPS and force-HTTPS. The worker has no HTTP surface; leave it with no domain. Web: static build served by nginx.
- Deploy by CLI per app (`caprover deploy -a <app> -b main` or tarball). The `-d`/subfolder behaviour was not covered by the fetched page; verify in the CLI docs.
- **Postgres + pgvector:** CapRover's one-click Postgres uses the stock `postgres` image, which has no `vector` extension. Create a plain app (no public domain) deployed with `imageName: pgvector/pgvector:pg16`, env `POSTGRES_PASSWORD`/`POSTGRES_DB`/`POSTGRES_USER`, and a **persistent directory** mapped to `/var/lib/postgresql/data` (pin it to one node if the swarm has several). Other apps reach it at `srv-captain--<db-app>:5432`. These are from my knowledge of CapRover conventions, not from the fetched page; verify at deploy time (Q32 already schedules deploy with the user).
- Infra ownership (per the global rule): there is no Terraform/Pulumi/Helm in this repo (`ls` shows only `docs/` and `fixtures/`), so CapRover app settings are configured in the CapRover UI/CLI by hand; the README deploy section is the record.

---

## E. SPEC AMENDMENTS

**E1 (§4 line 127-128, §13 #10): model ids.** Quote: "Exact default model ids are fixed during the spike against OpenAI's current docs, not guessed here."
Proposed: "Defaults: `EXTRACT_MODEL=gpt-6.1-sol`, `ASK_MODEL=gpt-6.1-terra`, `MAPPING_MODEL=gpt-6.1-terra`, `EMBED_MODEL=text-embedding-3-small` at 1536 dimensions. All overridable by config. Responses API; PDFs sent as `input_file` base64. (Confirm with the first live run: ids exist for the account and `gpt-6.1-sol` accepts PDF + strict json_schema together.)"

**E2 (§7.2 line 208-214 and §7.3 line 232-234): shrink the output.** Quote: "`entity` (fund or account), `entity_kind` ..., `share_class` ... `value_as_written`, `value`, `unit`, `currency`, `benchmark_name`, and a pointer ..."
Proposed: rows reference `funds[]` by `fund_index`; the model does not return `value` (code parses `value_as_written`, §7.3 already does and already prefers the parsed value). Add: "`max_output_tokens` is set to the model maximum, the client timeout is at least 10 minutes, and an `incomplete` response is treated as a retryable failure, not a repair case." Reason: estimated 20-25k output tokens for Man AHL at the current row shape (A.3). To be re-justified with measured numbers.

**E3 (§7.2 line 215-218 "Prompt rules"): add** "Percent values are returned as written; `n/a`, `n/m`, blanks and dash placeholders (`-`, en dash, em dash) produce no row." and add en/em dash to the §7.3 parser's no-value list. (Larchmont and Alderbank fixtures.)

**E4 (§7.2 line 224-229, CSV/xlsx).** Quote: "The model sees the header and the first 20 rows and returns a column mapping (long or wide layout; which columns are entity, date, measure, value; unit; header and footer rows to skip)."
Proposed: "The model sees the header region, the first 20 rows and the last 5 rows (footnotes), and returns a mapping with: layout; header row; skip-rows rule; entity and share-class columns; date column or wide month columns with a date format; a list of value columns each with `measure`, `period_kind`, `unit` (`percent_number | percent_string | fraction | currency`) and an optional `benchmark_name_column`; document currency; and per-entity `period_end` overrides taken from footnotes (for example the Alderbank Asia YTD ends 2026-08-31)." Evidence: A.5 (28/29 without the override; the one miss is exactly the footnote).

**E5 (§7.2 line 221-223): email/HTML cleaning.** Add: "Layout tables that wrap other tables are unwrapped; only innermost tables become pipe-delimited rows." Evidence: A.6 (Larchmont duplicated text without it).

**E6 (§5 line 145-149, Google app status).** Quote: "The spike confirms Google allows this with `drive.readonly`; if it doesn't, fall back to Testing mode plus a Reconnect banner."
Proposed: "Confirmed from Google's documentation (not yet from a live consent): an unverified Production app may request `drive.readonly`. Users see the 'Google hasn't verified this app' screen once; the project can have at most 100 new users in total over its lifetime. Testing mode expires authorisation and refresh tokens after 7 days. Keep `ALLOWED_EMAILS` well under 100. Final confirmation is the first successful sign-in with the real client (section G of the spike findings)." Remove the 'if it doesn't' hedge once that sign-in succeeds.

**E7 (§5): auth details to add.** "The authorisation request sets `access_type=offline` and `prompt=consent`, and a `state` value. If a token response has no refresh token, keep the stored one. A Drive 403/429 is retried with backoff; only `invalid_grant` sets `needs_reconnect`."

**E8 (§9 line 301-305): tool builder.** Add: "Each `ask` route must declare an explicit `operation_id` and a docstring (startup fails otherwise); tools are emitted with `strict: false` because optional parameters are not strict-compatible; the in-process request carries a server-minted internal credential for the asking user." Evidence: D.2.

**E9 (§10, §7.4): embeddings.** Add: "`chunk.embedding` is `vector(1536)` with an HNSW cosine index; `text-embedding-3-large` is only usable with `dimensions=1536` because HNSW tops out at 2000 dimensions." Evidence: D.1.

**E10 (§7.1): none needed.** Rule validated on all 7 fixture PDFs and generated scans (B).

---

## F. Still needs the user

1. **A working `OPENAI_API_KEY`.** The one in the environment gets `401 invalid_api_key` from `GET /v1/models`. Then run the command in A.7 (about $0.3-0.6) and send me, or read, the printed table plus `out/*.json`. Until then the model choice, latency, cost, trap behaviour and strict-schema acceptance are unmeasured.
2. **A Google OAuth client** (steps C.4), with test users or Publish app. Then run the probe (section G) and check: (a) refresh token present, (b) `parents` populated on a file someone else put in the folder, (c) `poll 2` sees a dropped file as `IN_FOLDER`, (d) the warning screen text in Production.
3. **CapRover access** for the last-step deploy (Q32): root domain, whether the swarm has one or several nodes (for the Postgres persistent directory), and a decision on a privacy-policy URL if the consent screen demands one.
4. Decide E2 (leaner row shape) before the plan fixes the database columns; it changes `common_row` only slightly (a `fund_id` instead of repeated strings, which the data model already has).

---

## G. Drive probe — exact run instructions

Prereqs: the OAuth client from C.4 with redirect URI `http://localhost:8000/auth/callback`; your Google account added as a test user (or the app published); a Drive folder you own with a couple of files (for example `fixtures/`), and its ID (the last segment of the folder URL). Port 8000 must be free.

```
export GOOGLE_CLIENT_ID=...            # from the console, do not commit
export GOOGLE_CLIENT_SECRET=...
cd /private/tmp/claude-501/-Users-ibrown-Code-claude-ai-equi-takehome/5f593e56-6a9a-478d-ba06-926e7e685e8f/scratchpad/spike
uv run --no-project --with google-auth-oauthlib --with requests python drive_probe.py --folder-id <FOLDER_ID> --wait 60
```
Open the printed URL, accept the warning (Advanced, then Go to ... unsafe), approve. The script then: prints granted scopes and whether a refresh token came back; calls userinfo; reads the folder; saves the start page token **first**; lists the folder with pagination; streams the first non-Google-native file with `alt=media`; polls `changes.list` immediately (poll 1), then waits `--wait` seconds while you add, trash or move a file in the folder, and polls again (poll 2), printing each change as `IN_FOLDER` or `other-folder`; finally refreshes the access token with the stored refresh token. It stores nothing on disk. Source (`drive_probe.py`):

```python
"""Throwaway Drive probe. Mirrors the app's web flow (one consent: openid email profile + drive.readonly, offline).
Run:  GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=... uv run --no-project --with google-auth-oauthlib --with requests \
        python drive_probe.py --folder-id <FOLDER_ID> [--wait 60]
Redirect URI registered on the client must be exactly http://localhost:8000/auth/callback"""
import os, sys, json, time, argparse, threading, secrets
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import AuthorizedSession, Request
SCOPES=["openid","https://www.googleapis.com/auth/userinfo.email","https://www.googleapis.com/auth/userinfo.profile","https://www.googleapis.com/auth/drive.readonly"]
REDIRECT="http://localhost:8000/auth/callback"; API="https://www.googleapis.com/drive/v3"
os.environ["OAUTHLIB_RELAX_TOKEN_SCOPE"]="1"   # Google may reorder/alias scopes (email -> userinfo.email)
def get_creds():
    cfg={"web":{"client_id":os.environ["GOOGLE_CLIENT_ID"],"client_secret":os.environ["GOOGLE_CLIENT_SECRET"],
        "auth_uri":"https://accounts.google.com/o/oauth2/v2/auth","token_uri":"https://oauth2.googleapis.com/token","redirect_uris":[REDIRECT]}}
    flow=Flow.from_client_config(cfg,scopes=SCOPES,redirect_uri=REDIRECT)
    state=secrets.token_urlsafe(16)
    url,_=flow.authorization_url(access_type="offline",prompt="consent",state=state)   # prompt=consent forces a refresh token every time
    got={}
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            q=parse_qs(urlparse(self.path).query)
            if urlparse(self.path).path!="/auth/callback": self.send_response(404); self.end_headers(); return
            got.update({k:v[0] for k,v in q.items()}); self.send_response(200); self.end_headers(); self.wfile.write(b"OK, return to the terminal.")
        def log_message(self,*a): pass
    srv=HTTPServer(("localhost",8000),H); print("\nOpen this URL in a browser:\n"+url+"\n")
    while "code" not in got and "error" not in got: srv.handle_request()
    if "error" in got: sys.exit("OAuth error: "+got["error"])
    assert got["state"]==state, "state mismatch"
    flow.fetch_token(code=got["code"]); return flow.credentials
def j(r):
    if r.status_code>=400: print("HTTP",r.status_code,r.text[:400])
    r.raise_for_status(); return r.json()
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--folder-id",required=True); ap.add_argument("--wait",type=int,default=60); a=ap.parse_args()
    c=get_creds(); print("granted scopes:",sorted(c.scopes or []))
    print("refresh_token present:",bool(c.refresh_token),"| expires in s:",int((c.expiry-__import__('datetime').datetime.utcnow()).total_seconds()))
    s=AuthorizedSession(c)
    print("userinfo:",j(s.get("https://openidconnect.googleapis.com/v1/userinfo")))
    f=j(s.get(f"{API}/files/{a.folder_id}",params={"fields":"id,name,mimeType,parents","supportsAllDrives":"true"})); print("folder:",f)
    # 1) token FIRST (spec §6 order), 2) then list
    tok=j(s.get(f"{API}/changes/startPageToken",params={"supportsAllDrives":"true"}))["startPageToken"]; print("startPageToken:",tok)
    files=[]; pt=None
    while True:
        p={"q":f"'{a.folder_id}' in parents and trashed=false","pageSize":100,"fields":"nextPageToken,files(id,name,mimeType,md5Checksum,size,modifiedTime,parents,trashed)",
           "supportsAllDrives":"true","includeItemsFromAllDrives":"true","orderBy":"name"}
        if pt: p["pageToken"]=pt
        d=j(s.get(f"{API}/files",params=p)); files+=d["files"]; pt=d.get("nextPageToken")
        if not pt: break
    print(f"files.list: {len(files)} item(s)")
    for x in files[:25]: print("  ",x["id"],x["mimeType"],x.get("size"),x.get("md5Checksum"),x["name"])
    first=next((x for x in files if not x["mimeType"].startswith("application/vnd.google-apps")),None)
    if first:
        r=s.get(f"{API}/files/{first['id']}",params={"alt":"media","supportsAllDrives":"true"},stream=True); n=0
        for chunk in r.iter_content(65536): n+=len(chunk)
        print("alt=media streamed",first["name"],"status",r.status_code,"bytes",n,"content-type",r.headers.get("content-type"))
    # 3) poll changes twice
    def poll(tok):
        out=[]
        while True:
            d=j(s.get(f"{API}/changes",params={"pageToken":tok,"pageSize":100,"includeRemoved":"true","supportsAllDrives":"true","includeItemsFromAllDrives":"true",
              "fields":"nextPageToken,newStartPageToken,changes(changeType,fileId,removed,time,file(id,name,mimeType,md5Checksum,trashed,parents))"}))
            out+=d["changes"]
            if "nextPageToken" in d: tok=d["nextPageToken"]
            else: return out,d["newStartPageToken"]
    for i in (1,2):
        if i==2:
            print(f"\n>>> Now drop/move/trash a file in the folder within {a.wait}s ..."); time.sleep(a.wait)
        t0=time.time(); ch,tok=poll(tok); dt=time.time()-t0
        print(f"poll {i}: {len(ch)} change(s) in {dt*1000:.0f} ms, next token {tok}")
        for x in ch:
            fl=x.get("file") or {}; inf=a.folder_id in (fl.get("parents") or [])
            print("   ",x["changeType"],"removed" if x.get("removed") else "", x["fileId"],fl.get("name"),"trashed="+str(fl.get("trashed")),"IN_FOLDER" if inf else "other-folder")
    # 4) prove the refresh token works (this is what the worker does every poll cycle)
    c.expiry=None; c.refresh(Request()); print("\nrefresh with stored refresh_token OK; new access token expires",c.expiry)
main()
```

---

## C (live run, 2026-10-28) — Drive probe run by the user

Run against "Equi Finance Docs" (folder id `1vMG2qvqZ5h74hzdyOstiUwGpslMobKhc`)
with the OAuth app in **Testing** mode (Q34) and the user as a test user.

- **Consent:** the unverified-app warning appeared and could be passed
  ("Advanced → Go to …"). Granted scopes included `openid`, `email`,
  `profile` and `drive.readonly` in one consent.
- **Refresh token:** present (`access_type=offline`, `prompt=consent`);
  access token about 3600 s; refreshing with the stored refresh token worked.
- **userinfo:** returned `email` = the user's account, `email_verified: true`
  (the allowlist check can key on it).
- **Folder read:** `files.get` on the folder worked; `files.list` with
  `'<id>' in parents` returned only the direct child (the `docs` subfolder),
  confirming subfolders need their own traversal (Q35).
- **Change polling:** `startPageToken` 149371; poll 1 returned 0 changes in
  145 ms. After the user dropped `Equi.png` directly into the folder, poll 2
  returned 1 change in 164 ms, with `parents` populated so the client-side
  folder filter classified it `IN_FOLDER`. The token advanced to 149374, so
  Drive skips tokens and the token must always be taken from the response.
- **Port clash found:** `localhost:8000` resolved to IPv6, where another
  local Docker app (`trust-ledger-api-1`) was listening; the probe was on
  IPv4 `127.0.0.1:8000`. **Plan decision:** the app's API defaults to port
  **8010**, and the local redirect URI uses **127.0.0.1**:
  `http://127.0.0.1:8010/api/auth/google/callback` (to be added to the
  Google client).
- **Python note:** `datetime.utcnow()` is deprecated (Python 3.12); use
  `datetime.now(UTC)`.

**Status:** the OAuth + Drive hard part is proven end to end, except subfolder
traversal and the CapRover redirect, which are built in the app.
