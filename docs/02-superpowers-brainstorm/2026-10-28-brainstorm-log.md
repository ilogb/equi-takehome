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

**Outcome.** The user picks a smaller subset of the real documents and gives
Claude a path. Claude makes 1–2 synthetic CSVs and emails to cover the gaps
(only one real CSV, no real emailed fund updates).
