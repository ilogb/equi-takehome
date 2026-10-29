# Document Intelligence

Connect a Google Drive folder of fund documents (PDF, CSV/xlsx, HTML/eml). The app
extracts performance figures, AUM and printed tables into Postgres, lets you search
and browse them with the source document alongside, and answers questions
("Analyze") using tools scoped to your own data.

**Privacy: documents you connect are sent to OpenAI for extraction, mapping, embeddings and Analyze.**

## Quick start

Get the app running locally in about 10 minutes.

### What you need

- **Docker Desktop**, running: https://www.docker.com/products/docker-desktop/
- **Git**
- **The `.env` file** Imran sent you
- **A Google account** that Imran has added to the app (the email you gave him)
- Free ports **5173**, **8000** and **5432** on your machine

You don't need Node, Python or a Google Cloud project; Docker builds everything.

### Run it

1. Clone the repo and go into it:

   ```bash
   git clone https://github.com/ilogb/equi-takehome.git
   cd equi-takehome
   ```

2. Put the `.env` file Imran sent you in the repo root (next to `docker-compose.yml`).
   It must be named exactly `.env`.

3. Start the app (the first build takes a few minutes):

   ```bash
   docker compose up --build
   ```

   It's ready when the log shows `worker started`. Leave this terminal running.

   If port 5432 is already in use, run `DB_PORT=5433 docker compose up --build` instead.

4. Open **http://localhost:5173**.

### Try it

1. **Sign in with Google** using the email you gave Imran.
   Google shows *"Google hasn't verified this app"* because the app is in testing mode:
   click **Continue**, then allow read-only Drive access.
2. **Choose a folder** of fund documents in your Google Drive. Either:
   - upload the sample documents in this repo's [`fixtures/`](fixtures/) folder (real
     factsheets plus synthetic statements, CSVs and emails) to a new Drive folder, or
   - pick a folder Imran has shared with you.
3. Watch the **Library**: files go from queued to processing to done in about a minute
   each, and the dashboard fills in as they finish.
4. Explore:
   - **Data**: every number from every document, with filters (fund, measure, period) and
     flags for values that need review or that two documents report differently.
   - **Find**: search document text, with similar documents.
   - **Analyze**: ask a question, e.g. *"Which fund had the best 1-year return as of
     September 2026?"*
   - Drop a new file into the Drive folder: it is picked up within a minute.

### Stop or reset

- Stop: `Ctrl+C` in the terminal (or `docker compose down`).
- Start again with your data: `docker compose up`.
- Wipe all data and start fresh: `docker compose down -v`, then `docker compose up --build`.

### If something goes wrong

| What you see | Fix |
|---|---|
| `Error 403: access_denied` or "isn't on the access list" when signing in | Your email isn't added yet: ask Imran. |
| `port is already allocated` | Another app uses 5173, 8000 or 5432: stop it, or use `DB_PORT=5433` for the database. |
| Files stay *queued* | Check the worker: `docker compose logs -f worker`. |
| A page shows an error after a restart | Wait for the API to finish starting, then refresh. |

## Stack

- Backend: FastAPI, SQLAlchemy, Postgres 16 + pgvector
- Models (OpenAI): `gpt-6.1-sol` extraction, `gpt-6.1-terra` CSV/xlsx mapping and Analyze, `text-embedding-3-small` embeddings
- Web: React 19, Vite, Tailwind 4, shadcn/ui, TanStack (Query, Table)

## Running it with your own keys

### Prerequisites

Everything in the quick start, plus:

- An **OpenAI API key**
- A **Google Cloud OAuth client** with the Drive API enabled (step 1 below)
- A **Google account** listed both under the OAuth app's **Test users** and in `ALLOWED_EMAILS`
- `make` is optional: it ships with macOS (Xcode command line tools) and most Linux; every
  `make` target below is a one-line command you can run directly

Only to run without Docker, or to run the tests:

- **Python 3.12** and **uv** (https://docs.astral.sh/uv/)
- **Node 22** and npm
- **Postgres 16 with pgvector**

### Setup

1. **Google client** (full steps: [spike findings section C.4](docs/03-implementation-plan/2026-10-28-spike-findings.md)):
   enable the Drive API, configure the consent screen as External and leave it in
   **Testing**, add yourself under **Test users**, create a Web application client with
   redirect URI `http://localhost:8000/api/auth/google/callback`.
2. `cp .env.example .env`, fill it in, and run `make keys` for `SESSION_SECRET` and `FERNET_KEY`.
3. Run it:
   - Docker: `make dev` (compose: db, api, worker, web), then open http://localhost:5173.
     If host port 5432 is taken, use `DB_PORT=5433 make dev`.
   - Without Docker: a Postgres with pgvector on :5432, then `make install` (Python and
     npm dependencies), `make migrate`, and in three shells `make api`, `make worker`,
     `make web`.

## Commands

| | |
|---|---|
| `make install` | Install dependencies for running without Docker: `uv sync` (backend) and `npm --prefix web ci` (web) |
| `make test` | Backend unit tests (no network, no DB). Web: `npm --prefix web test -- --run` |
| `make eval` | Live extraction eval against the fixtures. Calls OpenAI, costs about $1-2. **Results: pending.** |
| `make migrate` | `alembic upgrade head` (the API container also does this on boot) |

## Deploy

CapRover: see [deploy/caprover/README.md](deploy/caprover/README.md). The definitions are
`captain-definition-api`, `captain-definition-worker` and `captain-definition-web` at the repo
root. The `web` app proxies `/api`, so the Google redirect URI is on the web app's domain.

## Design history

How the design evolved, v0 to v3 ([docs/README.md](docs/README.md)):

- v0 [spec and plan, Claude alone](docs/00-only-claude-ai/)
- v1 [human brainstorm](docs/01-human-brainstorm/2026-10-28-human-brainstorm.md)
- v2 [brainstorm log](docs/02-superpowers-brainstorm/2026-10-28-brainstorm-log.md), [spec](docs/02-superpowers-brainstorm/2026-10-28-document-intelligence-design.md), [UI mockup](docs/02-superpowers-brainstorm/2026-10-28-document-intelligence-mockup.html)
- v3 [spike findings](docs/03-implementation-plan/2026-10-28-spike-findings.md), [implementation plan](docs/03-implementation-plan/2026-10-28-document-intelligence-plan.md)

## Known gaps

- Integration tests are deferred by decision: [deferred-integration-tests.md](docs/03-implementation-plan/deferred-integration-tests.md). Only unit tests exist.
- Scanned PDFs are flagged, not extracted (no OCR).
- Edits and deletes of files in Drive are ignored after the first sync (Q24).
- Google Testing mode means refresh tokens last a week: reconnect weekly.
- `make eval` results are pending.
