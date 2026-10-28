# Guided brainstorm log (v2)

> **Provenance.** Each entry records the question Claude asked, any
> recommendation Claude gave with it, the user's answer **verbatim**, and the
> user's reasoning **only as the user stated it**. Where the user gave no
> reason, the entry says so; Claude does not fill it in.
>
> **Where answers happen.** From Q4 on, questions are asked on a web page
> ("Equi Brainstorm Desk", https://claude.ai/artifact/K8pYyEf7gEVNwo35zmQMiT,
> source `brainstorm.html` in this folder) at the user's request: "I prefer
> html over reading from the terminal for the brainstorm". Claude copies each
> saved answer into this log verbatim.

## Q1 — Storing the example documents

**Context.** A recon agent found 29 real public documents from 20 sources
(factsheets, NAV/performance reports, sample statements, HTML reports, one
CSV). Several state redistribution limits (Man AHL, Milford; MSCI/Morningstar
data clauses), and four source links always serve the latest month, so a
download script stops being reproducible.

**Question.** Will the repo you hand in be public, and does that change how
you want to store these real documents?

**Claude's recommendation.** Commit the manifest (source URLs, sha256, notes)
and the expected values; keep the real files gitignored and restore them from
a private copy (the Google Drive test folder); commit the synthetic documents
so tests and grading always have something to run on.

**User's answer (verbatim).**
> Ok let me go thru the data, I agree can you make 1-2 synthetic csv and
> emails, I am going to create a new folder for you to read from to save and
> use for this project!
>
> no I am saying i am going to reduce the files for us to work with and give
> you a path to that, 20+ is a bit too much for this take home

**User's reasoning.** "20+ is a bit too much for this take home." Whether the
repo will be public was not answered.

**Follow-up answer (verbatim).**
> alright take these documents heres -> /Users/ibrown/Desktop/EquiTakeHome and
> the once you just created those syntehci ones in the repo
>
> and lets commit that
>
> no i nthis case I want the actual fils included these are public files and i
> need to share my repo with folks at equi

**User's reasoning.** "these are public files and i need to share my repo with
folks at equi."

**Outcome.** Claude's recommendation was **overruled**. The user chose 7 of the
29 real documents (Fundsmith ×2, Man AHL, iShares SWDA, JPMorgan JPEF, UVic
pension, TSP CSV), and they are committed in `fixtures/real/` with the
manifest, next to 4 synthetic documents in `fixtures/synthetic/`. The repo is
shared with Equi reviewers. Noted for the record: the Man AHL factsheet states
it "may not be reproduced … without prior written consent".

## Q2 — Search-first or numbers-first?

**Context.** The v1 notes lean on document search (vector search, "finds
something that I KNOW is inside of a file", similar results); the brief leans
on a cross-fund table of numbers and questions like "best January return".

**Question.** Picture the person using this on their first morning: are they
mostly hunting for a document or passage they know exists, or comparing
numbers across funds?

**User's answer (verbatim).**
> ok lets start with the brainstorming with what i wrote and things i might be
> missing and make sure to pay attention to the mvp. I wrote out all possible
> things just to show where my mind is but I want to get a running version
> first with the things in the MVP, pulling out tables and rendering them
> correctly and the google ouath might be the hardest parts with the auto sync

**User's reasoning.** The v1 notes list "all possible things just to show
where my mind is"; the priority is "a running version first with the things in
the MVP". The user names the hardest parts as table extraction and rendering,
Google OAuth, and auto-sync.

**Outcome.** The question was redirected rather than answered: scope is the
v1 MVP list, and the brainstorm works from the v1 notes plus gaps.

## Q3 — MVP playback and gaps

**Context.** Claude played back the MVP from the v1 notes and listed four gaps
against the brief: (1) no combined cross-document table, (2) natural-language
Q&A placed after the MVP, (3) "pull all files" vs the brief's designated
folder, (4) no link from each number to its source.

**Question.** When the app pulls a table out of a factsheet, do you want it
kept exactly as the document laid it out, or turned into common rows that
line up across every manager?

**User's answer (verbatim).**
> I think I do want a select one folder vs all as I plan to put the fixtures
> in my google account and i have a lot of other stuff there.

**User's reasoning.** "I plan to put the fixtures in my google account and i
have a lot of other stuff there."

**Outcome.** Gap 3 settled: **the user selects one folder**; the app ignores
the rest of Drive. The table question and gaps 1, 2 and 4 are still open.

## Q4 — Tables: as printed, or common rows?

*Asked on the web page, with real tables from `fixtures/real/` (Man AHL grid,
Fundsmith period row, UVic newest-first table) beside the same numbers as
common rows.*

**Question.** Which do you want: the tables as each manager printed them, the
common rows, or both?

**Options offered.** As printed · Common rows · Both.

**Claude's recommendation.** Both: common rows answer the brief's headline
question; the as-printed view is how a person checks them. Cost: two things
stored per table.

**User's answer (verbatim).** Choice: **Both**. (No extra text.)

**User's reasoning (verbatim).**
> I think as printed is nice to have for fund by fund search, question level.
> The common rows are the insights that make the search more than a search.

**Outcome.** Every extracted table is kept as printed (for per-fund browsing
and search) **and** turned into common rows (fund · period · measure · value)
that power the cross-fund table and questions. Each common row links back to
its cell in the printed table.

> **Format change after Q4.** The user, verbatim: "ok this is too slow lets
> keep it back in terminal and move faster with the questions and is this
> using superpowers brainstorm usually claude or something gives me questions
> and options and ability to move ot the next questino quickly". From Q5 on,
> questions are multiple-choice rounds in the terminal (several per round);
> the web page is retired. Recommended options were listed first and marked.

## Round 1 (Q5–Q8)

### Q5 — Stack
**Question.** Stack: Python/FastAPI + Postgres with pgvector + React/Vite, all
started with `docker compose up`. OK?
**Options.** Take defaults (recommended) · SQLite, no Docker · Streamlit front end.
**Answer.** Take defaults (Recommended).
**Outcome.** FastAPI, SQLAlchemy 2, Postgres 16 + pgvector, React/TS/Vite,
`docker compose up`.

### Q6 — Embedding model
**Question.** Which embedding model for vector search? (Claude has no
embedding API.)
**Options.** Local model (recommended) · Voyage AI · OpenAI embeddings · Skip
vectors for MVP.
**Answer (verbatim, typed as "Other").**
> I think im going to put the backend on cap rover with my key and locally yes
> they can put in their key so openAI is best on my side
**Reasoning.** As stated: the backend will be deployed on CapRover using the
user's own key; reviewers running locally supply their own key; so OpenAI.
**Outcome.** OpenAI embeddings. **New requirement:** a CapRover deployment
running on the user's key, plus local runs where reviewers bring their key.
Recommendation (local model) overruled.

### Q7 — Plain-English Q&A in the MVP?
**Question.** Is plain-English Q&A ("Which fund had the best January
return?") part of the MVP?
**Options.** Yes, simple version (recommended) · Yes, full agent · After MVP.
**Answer (verbatim, typed as "Other").**
> I guess we use open ai for this and we will give it a list of apis and what
> they do with swagger mainly, I believe in first having agent tools as "api"
> then on the second version it's easy to set up an agent and give it tools
**Reasoning.** As stated: build the capabilities as APIs first, described by
the OpenAPI (Swagger) spec; turning them into agent tools in a second version
is then easy.
**Outcome.** Q&A is in the MVP and uses **OpenAI**. The LLM is given the app's
own API endpoints (from the OpenAPI spec) as its tools. A full agent comes in
v2. The exact v1 shape is asked in Round 2.

### Q8 — Link each number to its source?
**Question.** Should every extracted number link back to where it came from
in the document?
**Options.** Yes: page + quote (recommended) · Yes: document only · Not for MVP.
**Answer.** Yes: document only.
**Outcome.** Each number links to its source document, not to a page or
quote. Recommendation (page + quote) overruled.

## Round 2 (Q9–Q12)

### Q9 — Extraction LLM provider
**Question.** Extraction (reading PDFs/emails/CSVs into tables) also needs an
LLM. Same provider as Q&A?
**Options.** OpenAI for everything (recommended) · Claude for extraction ·
Pluggable, OpenAI default.
**Answer.** Pluggable, OpenAI default.
**Outcome.** One small provider interface for LLM calls, with OpenAI as the
default; another provider can be swapped in through config.

### Q10 — Q&A v1 shape
**Question.** Q&A v1 using your own APIs as tools: how many calls can it make
per question?
**Options.** Small loop, max ~5 calls (recommended) · Single call · No LLM
call planning.
**Answer.** Small loop, max ~5 calls (Recommended).
**Outcome.** The model picks GET endpoints from the OpenAPI spec, the server
runs them, and the model may call again, up to about 5 calls, before
answering.

### Q11 — Who signs in to the deployment
**Question.** Who signs in to the CapRover deployment? (It uses your OpenAI
key and is on the public internet.)
**Options.** Allowlist of Google accounts (recommended) · Only me, demo mode ·
Anyone with the link.
**Answer.** Allowlist of Google accounts (Recommended).
**Outcome.** Google sign-in is the app login. Only allowlisted emails get in
(the user plus Equi reviewers, who are also added as test users on the Google
OAuth app). Each user sees only their own Drive data, so every row is scoped
to a user.

### Q12 — Auto-sync
**Question.** Auto-sync: how should new files in the folder be noticed?
**Options.** Poll every 60s + Sync now (recommended) · Push + poll fallback ·
Manual only.
**Answer.** Poll every 60s + Sync now (Recommended).
**Outcome.** The Drive Changes API is polled every 60 s, plus a Sync now
button. This behaves the same locally and on CapRover.

## Round 3 (Q13–Q16)

### Q13 — Document metadata
**Question.** "Good metadata" from your MVP: what does the LLM tag each
document with?
**Options.** Fixed fields + free tags (recommended) · Fixed fields only ·
Free-form tags only.
**Answer (verbatim, typed as "Other").**
> the free tags, i dont think we would put a ux and filter with those on the
> UI at least, vector search maybe
**Reasoning.** As stated: free tags wouldn't get a UI filter, but might help
vector search.
**Outcome.** Interpretation confirmed in Q17.

### Q14 — "Show similar results"
**Question.** "Show similar results": similar how?
**Options.** Same fund/manager + vector neighbours (recommended) · Vector
neighbours only · Not in MVP.
**Answer.** Same fund/manager + vector neighbours (Recommended).
**Outcome.** Similar results show documents for the same fund or manager first
(for example Fundsmith January and August), then the nearest documents by
embedding.

### Q15 — File types
**Question.** Which file types does the MVP handle? (multi-select)
**Options.** PDF · CSV · HTML / .eml emails · Google Docs/Sheets.
**Answer.** PDF, CSV, HTML / .eml emails.
**Outcome.** PDF, CSV, HTML and .eml are in. Google-native Docs/Sheets are
out of the MVP.

### Q16 — Measuring extraction quality
**Question.** How do we know extraction is right?
**Options.** Score vs truth files (recommended) · Truth files + LLM judge ·
Unit tests only.
**Answer.** Score vs truth files (Recommended).
**Outcome.** `make eval` runs extraction over the fixtures and scores the
results against the `.truth.json` files (precision and recall per document).
No judge model.
