# Human brainstorm (v1, no AI assistance)

> **Provenance.** Written by the user alone, before any AI-assisted brainstorm.
> The original is `2026-10-28-human-brainstorm.png`; below is a verbatim
> transcription (spelling kept as written) so it can be diffed and quoted.
> Nothing here was changed or added by Claude.
>
> **Update.** Later the same day the user added "Landing Dashboard" to both lists; the
> updated picture is `2026-10-28-human-brainstorm-v2.png` (the original is kept as it was).
> The two added lines are marked *(added in v2)* below.

## Work Backwards from the goal?

- We want the UX to hide as much complexity as possible
  - RBAC
    - Think of different roles from a view and edit point of view
    - Admin → Can maybe look at the library of files in the system and remove it from showing up in search
      - extra credit but maybe some fund managers only have access to some folders or data, ideally their IT solved that internally but could be quite easy to configure for the admin - stretch goal i would skip this.
    - Fund Manager →
      - View Only → Main problem to solve first, all documents in the google drive are automatically pulled, we should allow them to select the exact folders they want f thats possible but starting with all folders is fine
- Google Drive Integration / Modular enough for drop box or any folder of files from a 3rd party Service
  - Quota limits?
    - This will determine if we sync done and pay the storage cost to avoid google rate limiting, we could also figure out a way of newly adding files, looking for some type of watch api, or something we can poll to see if something is added
  - api documentation and integration steps
- SEARCH and Retrieve
  - Fast search across all documents but the ability to see the path and potentially a hyperlink to render the document in platform. Google Drive is another app and if we can have the user stick in one app we should do that.
  - Assuming we index and put good meta data for the vector search, I would lean on accuracy over speed.
    - Sure no one wants a slow system but whats more frustrating is losing confidence that the system finds something that I KNOW is inside of a file. So tune for accuracy first. Caching and background cron jobs can help with speed later. I am making the assumption that the user would wait let's say 15 seconds max for a correct quality response vs fast but missing data one.
  - Good categorization will allow quick filters from the backend
  - After it's easy to throw a prompt that looks at our filters, api's and can take a users plan text and convert to a query
  - Super Intellegent Search that might need to run agent tools become a thing and for first pass, we may skip an agent system but we need to create "tools" or "apis" in the backend that the LLM can make to answer queries that may need to look a bunch of docs and pull out numbers and calculations
- Landing Dashboard *(added in v2)*
- Scaling
  - Cron Jobs
  - Caching → LLM level, FE level, BE level
  - Agent Ochestration Caching
  - LLM deepeval (LLM Judge)
- Testing
  - Find good example docs for the problem early
  - Unit tests, integration tests (lean here with Docker it's an api heavy app)
  - LLM guardrails
  - E2E tests if time permits

## MVP

- Find Example Fund Files
- Integrate with only with Google Drive
- Pull all files
- LLM parse and categorize with good meta data
- Run a good vector search with smart cosign rankings
- create a simple UX that searches and returns results with some of the metadata
- Show similar results as well with good categorization
- See if we can identify tabular data and numbers and render them as such on the ui.
  - We would first use LLM to spot them, then store a mapping to file of raw data in a fast format to query on.
- Landing Dashboard Page *(added in v2)*
