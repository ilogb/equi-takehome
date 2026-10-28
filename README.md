# Document Intelligence

Connect a Google Drive folder of fund documents (PDF, CSV/xlsx, HTML/eml). The app
extracts performance figures, AUM and printed tables into Postgres, lets you search
and browse them with the source document alongside, and answers questions
("Analyze") using tools scoped to your own data.

## Stack

- Backend: FastAPI, SQLAlchemy, Postgres 16 + pgvector
- Models (OpenAI): `gpt-6.1-sol` extraction, `gpt-6.1-terra` CSV/xlsx mapping and Analyze, `text-embedding-3-small` embeddings
- Web: React 19, Vite, Tailwind 4, shadcn/ui, TanStack (Query, Table)

**Privacy: documents you connect are sent to OpenAI for extraction, mapping, embeddings and Analyze.**

## Setup

1. **Google client** (full steps: [spike findings section C.4](docs/03-implementation-plan/2026-10-28-spike-findings.md)):
   enable the Drive API, configure the consent screen as External and leave it in
   **Testing**, add yourself under **Test users**, create a Web application client with
   redirect URI `http://localhost:8000/api/auth/google/callback`.
2. `cp .env.example .env`, fill it in, and run `make keys` for `SESSION_SECRET` and `FERNET_KEY`.
3. Run it:
   - Docker: `make dev` (compose: db, api, worker, web), then open http://localhost:5173.
     If host port 5432 is taken, use `DB_PORT=5433 make dev`.
   - Without Docker: a Postgres with pgvector on :5432, then `make migrate`, and in
     three shells `make api`, `make worker`, `make web`.

## Commands

| | |
|---|---|
| `make test` | Backend unit tests (no network, no DB). Web: `npm --prefix web test -- --run` |
| `make eval` | Live extraction eval against the fixtures. Calls OpenAI, costs about $1-2. **Results: pending.** |
| `make migrate` | `alembic upgrade head` (the API container also does this on boot) |

## Deploy

CapRover: see [deploy/caprover/README.md](deploy/caprover/README.md). The `web` app proxies
`/api`, so the Google redirect URI is on the web app's domain.

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
