# Frontend visual audit: D5 new-entry tab carry (2026-11-26)

Item D5, branch `wi/ui/sourdough/D5`, audited sha 3b4c56a1. Skill `frontend-visual-audit` (Playwright, Chromium). Scratch DB: copy of `data/demo.sqlite` migrated with a login user, served with `tests.visual.frozen_server` at 2026-10-31 on a free port. Never `data/budget.sqlite`. Change: the dialog tabs (happened / planned / repeats) carry the typed amount, category, account and note via `hx-include="closest form"` + `hx-params="not _csrf_token"`; `form_responses.open_new_entry` prefills with `posted`.

## Routes x viewports

Route: `/today` with the new-entry dialog (`n`), through all three tabs, the failing saves and a planned save. Rows: 1440, 1024, 375 light; 1440 dark. Diagnostics taken on /today, the dialog on each tab, after each failing save and after the save (9 snapshots per row, all identical per row).

| Route | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /today + new-entry dialog | 1440 | false | 0 | 0 | 0 (3 forced 422 resource logs) | 0 |
| /today + new-entry dialog | 1024 | false | 0 | 0 | 0 (3 forced 422) | 0 |
| /today + new-entry dialog | 375 | false | 1 (pre-existing) | 0 | 0 (3 forced 422) | 0 |
| /today + new-entry dialog | 1440 dark | false | 0 | 0 | 0 (3 forced 422) | 0 |

"Forced 422": Chromium logs "Failed to load resource ... 422" for the intentional empty-amount saves; no script errors.

Pre-existing overflowingElements at 375 (no CSS changed by D5; the diff is `form_responses.py` + two attributes in `new-entry.html`): `pre.rd-hero__loaf` right=399 on /today (decorative, absolutely positioned inside an `overflow: hidden` hero) and `label.rd-chip-option` right=384-395 in the dialog (the nowrap `overflow-x: auto` recents row, same finding as the F9 audit). No horizontal scroll.

## Behaviour checks (all four rows identical)

- Typed 35.50, Takeaway, Credit Card, note "lunch" on happened. planned: amount 35.50, Takeaway, Credit Card, lunch all kept. repeats: all kept, amount shows in the repeats amount field (`default_amount` = 35.50), note in `default_description`, cadence reset to monthly. Back to happened: all four kept (amount 35.50, Takeaway, Credit Card, lunch).
- Tab request: `GET /add?when=planned&dialog=1&amount=35.50&category=21&account_id=5&operation_date=2026-10-31&description=lunch`. No `_csrf_token` in any GET query string (the only "csrf" matches are the static `csrf.js` / `htmx-csrf.js` file names).
- Failing save per tab (amount cleared), the form has the native `required`, so the first click is stopped by the browser ("Please fill out this field.", dialog stays, values kept). With `required` removed the server answers 422 and the dialog stays open with the visible field error "▲ amount must be a decimal number within range" (current copy, not "Enter an amount above 0.00") on happened, planned and repeats; category, account and note stay.
- Successful planned save (35.50, Takeaway): POST /planned 200 with `HX-Refresh: true`, dialog gone, the item "lunch d5 audit . Credit Card, -35.50 PLN" appears under Upcoming on /today and in the ledger planned view. No flash text appears: the success path is a full refresh (not changed by D5; observation only).

## Step 3b

- Swap targets: `#modal-root`, `#modal-root .rd-dialog__hero`, `#credit-line` match exactly one element on each tab (the repeats `find .rd-formula__result` is an htmx relative selector, valid, not a CSS selector); duplicate ids 0 after every swap.
- Failing saves: forced 404, 409, 500 on POST /transactions, /planned, /recurring: the dialog stays open and shows a visible error each time ("That item was not found...", "That item changed in the meantime...", "Something went wrong on our side. Try again."); not left looking saved.
- Template logic: `rg` of `new-entry.html` for `float`, `/ 100`, `* 100`, `{% set`: no match; D5 adds only two attributes.
- Rendered numbers: the carried amount is the typed text; the hero is re-rendered by the server (`hero=1`); the Upcoming row shows -35.50 PLN, the posted value. No derived number is computed in the template.
- Listeners: no new HX-Trigger events.

## Findings

None blocking. Observations: (1) the empty-amount error copy is "amount must be a decimal number within range" (brief expected "Enter an amount above 0.00" or current copy); (2) planned save gives no flash text (full refresh instead).

## Screenshots

Scratchpad `shots/` (not committed), viewed: `375__repeats.png` (carried 35.50, Takeaway checked, Credit Card, lunch), `1440__saved.png` (planned item under Upcoming). Others per viewport: `<vp>__today|happened-typed|planned|repeats|happened-back|fail-<tab>|saved.png`.
