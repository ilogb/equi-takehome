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
