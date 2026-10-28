# Quick start (reviewers)

Get the app running locally in about 10 minutes.

## What you need

- **Docker Desktop**, running: https://www.docker.com/products/docker-desktop/
- **Git**
- **The `.env` file** Imran sent you
- **A Google account** that Imran has added to the app (the email you gave him)
- Free ports **5173**, **8000** and **5432** on your machine

You don't need Node, Python or a Google Cloud project; Docker builds everything.

## Run it

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

## Try it

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

## Stop or reset

- Stop: `Ctrl+C` in the terminal (or `docker compose down`).
- Start again with your data: `docker compose up`.
- Wipe all data and start fresh: `docker compose down -v`, then `docker compose up --build`.

## If something goes wrong

| What you see | Fix |
|---|---|
| `Error 403: access_denied` or "not on the access list" when signing in | Your email isn't added yet: ask Imran. |
| `port is already allocated` | Another app uses 5173, 8000 or 5432: stop it, or use `DB_PORT=5433` for the database. |
| Files stay *queued* | Check the worker: `docker compose logs -f worker`. |
| A page shows an error after a restart | Wait for the API to finish starting, then refresh. |

Documents you connect are sent to OpenAI for extraction and answers. More detail is in the
[README](README.md).
