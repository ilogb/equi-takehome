# Spike code (throwaway)

Scripts and raw outputs behind `../2026-10-28-spike-findings.md`. Not app
code: no tests, not maintained. Keys are read from the repo's gitignored
`.env` or the environment; nothing secret is stored here.

| File | What it was for |
|---|---|
| `live.py`, `run_extract.py`, `schema.py`, `strict.py`, `lean.py`, `est.py` | Live OpenAI extraction (§A): strict schema, current vs lean row shape, token estimates |
| `score.py`, `lenient.py` | Scoring against `fixtures/**/*.truth.json`, strict and lenient (E12) |
| `csvmap.py`, `live_csv.py`, `xl.py`, `nw.xlsx`, `nw_from_xlsx.csv` | CSV / `.xlsx` column mapping (§A, E4) |
| `txt.py`, `manahl.txt` | Email cleaning and PDF text layer checks |
| `scan.py`, `scanned*.pdf` | Scanned-PDF detection rule (§B) |
| `drive_probe.py`, `run_probe.sh` | Google OAuth + Drive probe the user ran (§C live) |
| `pgv.py` | pgvector + SQLAlchemy check (§D.1) |
| `tools.py` | OpenAPI `ask` routes as OpenAI tools, in-process (§D.2) |
| `out/` | Raw model JSON from the live run (`cur_*` current shape, `lean_*` lean shape, `map_*` CSV mappings) |
