# Header search: mode switch and search button

Mockup: [2026-10-28-header-search-mockup.html](2026-10-28-header-search-mockup.html)
([published](https://claude.ai/artifact/J6bVPaRtt2ckWk5AVR388k)).

Request: "the find and analyze should be a toggle, clicking a search icon should trigger or
pressing enter".

## Decisions

| # | Question | Chosen |
|---|---|---|
| 1 | Layout | **A**: segmented Find / Analyze switch after the field (TabsList look), search button inside the field. Chosen by the user. |
| 2 | Search button | Ghost icon inside the field; muted when empty, primary when there is text. |
| 3 | Empty query | Button `aria-disabled` (stays focusable), tooltip "Type something to search"; Enter and click do nothing. |
| 4 | Mode switch on `/search` | Re-run at once if the box still holds the query in the URL; if edited, only switch and wait for Enter / click. |
| 5 | Same query and mode submitted again | Re-run (refetch), showing the loading state. |
| 6 | Box contents | On `/search` mirror the URL, including Back / Forward; elsewhere keep the last query. |
| 7 | Narrow widths | Keep the words; Analyze placeholder is "Ask about your funds" below `md`. |
| 8 | Default mode off `/search` | Find. |

Decisions 2-8 are the mockup's recommendations, taken as defaults when the user picked A.

## Also fixed

- The box read the URL once on mount, so Back / Forward left stale text and mode (decision 6).
- The browser's own clear "x" on `type="search"` is hidden; it would sit beside the new button.

## Not in scope

Header loading indicator during an Analyze run; Escape-to-clear; a keyboard shortcut to focus
the box; the dark-mode contrast of the selected TabsTrigger (app-wide, unchanged here).
