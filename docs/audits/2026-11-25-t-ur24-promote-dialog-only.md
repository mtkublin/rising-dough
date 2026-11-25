# Frontend visual audit: T-UR24 promote is dialog only

Task: T-UR24, branch wi/ui/sourdough/UR24, audited head 593cb027. ADR-0027, ADR-0107, ADR-0134 section 5, ADR-0150.
Change: removed `GET /planned/{id}/promote/inline` and `GET /recurring/{id}/promote/inline`, the inline row and slide-over templates, the legacy
`?dialog=` branches and the unused `.rd-promote-inline*` CSS. Promote is the dialog `pages/entries/promote.html` only.
Method: frontend-visual-audit skill, Playwright chromium, own uvicorn on 127.0.0.1:8791 over a migrated scratch copy of data/demo.sqlite
(extra planned rows inserted in the scratch copy only). MAIN (ui/sourdough, `git archive`) served on :8792 over a second copy for the pre-existing check.
Heavy lock /tmp/ui-redesign-heavy.lock taken and released. data/budget.sqlite not touched.

## Routes and viewports

Routes x (1440, 1024, 375): `/today` (upcoming rows, promote opener), `/ledger`, `/ledger?view=planned` (row button at md and up, row menu item
below md), `/ledger?view=recurring` (row menu, promote), and the promote dialog itself opened from each of these. 3 viewports x 4 pages, plus per
viewport the dialog states: opened, 422 (amount 0 and empty), forced 404/409/500, success.

## Diagnostics (page loads, dialog open, after each swap)

| Route | 1440 | 1024 | 375 |
|---|---|---|---|
| /today | 0/0/0/0/0 | 0/0/0/0/0 | hs 0, overflowing 1 (pre-existing), 0/0/0 |
| /ledger | 0/0/0/0/0 | 0/0/0/0/0 | hs 0, overflowing 1 (pre-existing), 0/0/0 |
| /ledger?view=planned | 0/0/0/0/0 | hs 0, overflowing 21 (pre-existing), 0/0/0 | hs 0, overflowing 1 (pre-existing), 0/0/0 |
| /ledger?view=recurring | 0/0/0/0/0 | hs 0, overflowing 109 (pre-existing), 0/0/0 | hs 0, overflowing 1 (pre-existing), 0/0/0 |
| promote dialog (today, planned tab, recurring tab) | 0/0/0/0/0 | 0/0/0/0/0 | same as the page behind it |

Column order: horizontalScroll / overflowingElements / duplicateIds / consoleErrors / requestFailures (the three trailing values on the pre-existing
rows are duplicateIds / consoleErrors / requestFailures, all 0). duplicateIds 0 and requestFailures 0 on every page and after every swap.
consoleErrors 0 on every page load and dialog open; the only console lines are the browser's "Failed to load resource ... 422/404/409" for the
deliberate failing saves, which are expected.

Pre-existing overflowingElements, identical on MAIN (same element lists, same counts, checked on :8792 at 1024 and 375 on all four routes):
- 375 `/today`: `pre.rd-hero__loaf` right edge 399 (decorative loaf, clipped, no page scroll).
- 375 `/ledger*`: `a.rd-tabs__tab` right edge 380 (tab strip, scrolls inside its container).
- 1024 `/ledger?view=planned` and `?view=recurring`: `th`, `td.rd-row__actions`, `button.rd-btn`, `svg` right edge 1058: the table's actions column
  is wider than the panel and clipped (screenshot `1024_ledger_planned.png`: the `promote` button is cut off at the right edge). Not caused by T-UR24.

## Behaviour checks

- Removed URLs: `GET /planned/1/promote/inline`, `GET /recurring/1/promote/inline` and `.../promote/inline?dialog=1` all 404 at every viewport.
  `promote/inline` appears in none of the rendered HTML of the 4 routes at 3 viewports. No remaining `rd-promote-inline` in `src/` or the served CSS.
- Openers: `/today` upcoming rows have `a.rd-btn[hx-get=/planned/N/promote?dialog=1]` and `/recurring/N/promote?dialog=1`, target `#modal-root`.
  Ledger planned tab: row button visible at 1440, 1024 and 375 (the phone menu entry is hidden at md and up); recurring tab: row menu item.
  All open the dialog in `#modal-root`. A plain (non-HX) `GET /planned/N/promote` returns 200 with the `<dialog>` fragment, no full page.
- 422: amount `0` and empty amount, from `/today` planned, `/today` recurring, ledger planned and ledger recurring, at all 3 viewports: the dialog
  stays open, the hero shows "amount must be positive" and the summary shows "1 field needs attention / Amount: amount must be positive". Screenshots
  `*_today_422_zero.png`, `*_today_422_empty.png`, `*_ledger_planned_422.png`, `*_ledger_rec_422.png`.
- Forced 404, 409, 500 on the planned promote post (route intercept, from `/today`): the dialog stays open with a visible alert line
  ("That item was not found...", "That item changed in the meantime. Reload and try again.", "Something went wrong on our side. Try again."). 500 also
  forced on the recurring promote post from the ledger recurring tab: dialog open, error visible.
- Success: ledger planned tab: toast "Planned entry promoted", tab count 7->6, 5->4, 3->2 (1440/1024/375), row shows "promoted", row menu buttons remain.
  Ledger recurring tab: toast "Recurring occurrence promoted", the rule moved to its next due date, tab count stays 27, row menu buttons remain (27).
  `/today`: success post returns `HX-Trigger` ledger/forecast/(balance|budget)-stale and `HX-Refresh: true`; the page reloads, the promoted row is gone and
  the upcoming list refills (see finding 1 for the toast).
- Swap targets: every `hx-target` selector on the 4 pages matches exactly one element after load and after each swap (badswap empty).
- Events: the emitted `ledger-stale`, `forecast-stale`, `balance-stale`, `budget-stale` are the ones the ledger, today and plan pages listen to (unchanged by T-UR24).

## Step 3b

- Templates in the diff are deletions only (4 templates removed); the live templates `pages/entries/promote.html`, `fragments/rows/upcoming-row.html`,
  `planned-row.html` carry no `float`, `/ 100`, `* 100`, `{% set`. Amounts come through the view models.
- Rendered number equals the service value: planned row 223980 minor shows -2,239.80 in the row and prefills 2239.80 in the dialog; a recurring row
  +16,213.97 prefills 16213.97. The demo DB has no non-PLN account currency (the "Checking EUR" account stores PLN) and no JPY account, so the zero-decimal
  case could not be exercised on this data; the dialog money path was not changed by T-UR24.
- Every failing save shows a visible error (422, 404, 409, 500 above); none leaves the dialog looking saved.

## Screenshots (viewed)

Scratch dir `/tmp/claude-0/-home-user-rising-dough/86228838-e551-5ec3-979b-dd5580a5d147/scratchpad/UR24/shots/` (not committed), prefix `1440_`, `1024_`, `375_`:
`today`, `ledger_actual`, `ledger_planned`, `ledger_recurring`, `today_dialog`, `today_422_zero`, `today_422_empty`, `today_forced404/409/500`,
`today_rec_dialog`, `today_rec_422`, `ledger_planned_menu`, `ledger_planned_dialog`, `ledger_planned_422`, `ledger_rec_menu`, `ledger_rec_dialog`,
`ledger_rec_422`, `ledger_rec_forced500`, `*_after*`. Viewed: `1440_ledger_rec_422`, `375_today_422_zero` (bottom sheet, hero error and summary readable,
no clipping), `1024_ledger_planned` (the pre-existing clipped promote button).

## Findings

1. Behavior, low, pre-existing (code path unchanged by T-UR24): on `/today` a successful promote answers `HX-Refresh: true` (`web/htmx.py`
   `refresh_unless_on(..., LEDGER_PATH)`), so the page reloads and the success toast ("Planned entry promoted" / "Recurring occurrence promoted") is never
   shown. On `/ledger` the toast shows. Triage: not a T-UR24 regression; a flash that survives the reload (or a today-stale refresh instead of HX-Refresh) is the fix.
2. Layout, pre-existing on MAIN: 1024 planned and recurring tabs clip the actions column (promote button cut at the right edge), 109/21 overflowing elements.
3. Minor leftovers: the inert `?dialog=1` query still on the promote links (`fragments/rows/upcoming-row.html`, `web/ledger_view.py:636` menu item), and a
   stale comment in `pages/today/index.html:114` ("target of the inline promote fragments, which stay routed until T-UR24").
