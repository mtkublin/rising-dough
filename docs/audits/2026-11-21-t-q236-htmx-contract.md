# Frontend audit: T-Q236 HTMX error flashes and event contract

Change: T-Q236 (Q-037, Q-038; ADR-0142). Templates touched: `today/index.html` (hero and upcoming regions),
`accounts/index.html` (hero), `budget/index.html` (pace and summary sections), `settings/_categories.html`
(category list wrapper); each gains `id` + `hx-get`/`hx-trigger="<event> from:body"`/`hx-select`/`hx-swap`/
`hx-disinherit` so the four formerly orphan `*-stale` events re-fetch their panel. JS: `static/js/app-init.js`
(global `htmx:beforeSwap` error handler, `sendError`/`timeout` flash, undo reload only on success),
`users-admin.js` (own 409 rule removed).

Run: `frontend-visual-audit` method (Playwright, headless Chromium), app on a migrated scratch copy of
`data/demo.sqlite` (scratchpad `t236/scratch.sqlite`, never `data/budget.sqlite`), logged in through the real form.
Script and raw results: scratchpad `t236/audit.py`, `t236/audit.json`.

## Routes and diagnostics

Routes: `/today`, `/ledger`, `/ledger?view=planned`, `/budget`, `/accounts`, `/settings`,
`/settings?tab=categories` (ledger, planned, budget, accounts, settings; recurring and planned forms open from
Today and Ledger), each at 1440, 1024 and 375 (21 runs, all HTTP 200).

| Diagnostic | Result |
|---|---|
| horizontalScroll | false in all 21 runs |
| overflowingElements | 0 except `/budget` (297 at 1440, 535 at 1024, 884 at 375), `/ledger` 387 and `/ledger?view=planned` 17 at 375; all with `horizontalScroll` false (table cells inside scroll wrappers; this change adds attributes only, no CSS or markup structure) |
| duplicateIds | 0 in all runs, and 0 again after firing all four stale events |
| consoleErrors | 4 in every run: the browser's own "Failed to load resource" lines for the four forced 404/409/422/500 responses; no page error, none otherwise |
| requestFailures | 0 in all runs |

## Step 3b

1. Swap targets: every region selector (`#today-hero`, `#upcoming-root`, `#accounts-hero`, `#left-daily-spend`,
   `#budget-summary`, `#settings-categories`) matches exactly one element before and after the stale re-fetch
   (duplicateIds empty after the swap). G12 checks static `hx-target` ids.
2. Failing saves are visible: on every route a forced 404, 409, 422 and 500 (route interception of an
   `htmx.ajax` POST, server flash partial as body) shows the text in `#flash-region-assertive`; for 404/409/500 the
   originating target keeps its content, 422 form re-render swaps. e2e `test_htmx_error_flash.py` also covers plain
   text bodies (403/404/409/500 give the generic flash) and a network failure ("Could not reach the server").
3. No arithmetic in touched templates: the edits add attributes and a wrapper `div`; the URL is
   `request.url.path` plus the query string, no computation.
4. Money formatting: no number-producing markup changed (JPY/non-PLN not re-checked, unchanged by this task).
5. Rendered number equals the service value: unchanged; re-fetch returns the same server render.
6. Listeners: every `Event` is emitted and has a listener (G12 strict, zero allowlist); after firing
   `today-stale`, `balance-stale`, `budget-stale`, `settings-categories-stale` each page issued the self re-fetch
   (counts 2, 5, 8, 7 requests on Today, Accounts, Budget, Settings; Ledger has no such region).
7. Scratch data only (copy of `data/demo.sqlite`).

## Screenshots

`scratchpad/t236/shots/{desktop,tablet,mobile}__<route>.png` (21 files). Viewed `mobile___today.png`: shell, hero,
net worth, upcoming list render; no missing content, no flash left visible.
