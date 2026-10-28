# Design history

The take-home is Option A (Document Intelligence Web App, Google Drive). Specs
and plans are kept as numbered versions so each stage of thinking stays
visible next to the others. Earlier versions are never edited in place; a new
stage gets a new folder.

| Version | Folder | Who drove it | What it is |
|---|---|---|---|
| v0 | `00-only-claude-ai/` | Claude alone, zero guidance | Spec + plan written from the brief with no input from the user. Baseline. |
| v1 | `01-human-brainstorm/` | The user alone, no AI | The user's own high-level approach: original image + verbatim transcription. |
| v2 | `02-superpowers-brainstorm/` | The user + Claude (superpowers:brainstorming) | `2026-10-28-brainstorm-log.md` (Q1–Q32, answers verbatim) · the spec (`…-design.md`, readable as `…-design.html`) · the UI mockup (`…-mockup.html`, open in a browser; needs internet for Tailwind). |
| v4 | `04-build/` | Claude (subagent-driven build) | `2026-10-28-build-ledger.md`: every task, review, fix round and ruling made during the build. |
| v3 | `03-implementation-plan/` | Claude, from the approved spec + amendments | Spike findings (live OpenAI and Drive runs) with the spike code in `spike/`, and the implementation plan (`…-plan.md`). |

Each folder holds dated files: `YYYY-MM-DD-<topic>-design.md` (spec) and
`YYYY-MM-DD-<topic>-plan.md` (plan), plus any Q&A log or mockups for that stage.
