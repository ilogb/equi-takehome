# CapRover deployment

The browser only talks to the `web` app. `web` serves the SPA and proxies `/api`
to the API, so the session cookie is same-origin and the Google redirect URI
lives on the **web** app's domain.

## Apps

| App | Definition | Notes |
|---|---|---|
| `db` | One-click app or custom image `pgvector/pgvector:pg16` | Persistent directory on `/var/lib/postgresql/data`. Env: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`. Not exposed publicly. |
| `api` | `captain-definition-api` | Runs `alembic upgrade head`, then uvicorn on 8000 (HTTP port 8000). |
| `worker` | `captain-definition-worker` | No HTTP; same code, `python -m app.jobs.worker`. |
| `web` | `captain-definition-web` | nginx on port 80; enable HTTPS. Env: `API_UPSTREAM=srv-captain--api:8000`. |

The three definition files live at the **repo root** (`captain-definition-api`,
`captain-definition-worker`, `captain-definition-web`), so their `dockerfilePath`
(`./backend/Dockerfile`, `./web/Dockerfile`) and the Dockerfiles' `COPY` paths all resolve
against the repo root, which is the build context. `api` and `worker` use the same
`backend/Dockerfile`; the worker app sets `APP_ROLE=worker`, which makes the image run
`python -m app.jobs.worker` instead of migrations + uvicorn. In each app's Deployment tab
(deploy from Git) set "Captain Definition Relative Path" to
`./captain-definition-<api|worker|web>`.

**Deploy api before worker**: the api runs `alembic upgrade head` on boot; a worker that
starts against an unmigrated database fails its polls until the api has run.

**Deploy api before web**: nginx in `web` fails to start if the api host does not resolve.

## Env vars (api and worker)

```
DATABASE_URL=postgresql+psycopg://<user>:<password>@srv-captain--db:5432/<dbname>
OPENAI_API_KEY=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
ALLOWED_EMAILS=a@example.com,b@example.com
SESSION_SECRET=...            # make keys
FERNET_KEY=...                # make keys; same value on api and worker
PUBLIC_BASE_URL=https://<web-app>.<root-domain>
FRONTEND_URL=https://<web-app>.<root-domain>
FORWARDED_ALLOW_IPS=*          # api only: trust CapRover's proxy headers (https scheme)
# worker app only: APP_ROLE=worker
```

## Google client

- Add the authorized redirect URI `https://<web-app>.<root-domain>/api/auth/google/callback`.
- The app stays in Testing mode: add every reviewer as a test user. Tokens expire
  weekly, so users reconnect about once a week.
- Redirect URI edits can take a few minutes to apply.

## Smoke test

Open the web URL, sign in, choose the Drive folder, wait for a sync, run Analyze.
