# Guided brainstorm log (v2)

> **Provenance.** Each entry records the question Claude asked, any
> recommendation Claude gave with it, the user's answer **verbatim**, and the
> user's reasoning **only as the user stated it**. Where the user gave no
> reason, the entry says so; Claude does not fill it in.

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
