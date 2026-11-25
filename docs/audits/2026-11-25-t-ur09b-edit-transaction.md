# Audit: UR09b edit-transaction dialog on the shared dialog shell (2026-11-25)

## Scope

Change: T-UR09b (ADR-0107, ADR-0152). Branch `wi/ui/sourdough/UR09b`. `GET /transactions/{id}/edit` (dialog, hero refresh with `hero=1`, plain-load shell page), `POST /transactions/{id}` (save, 422), `POST /transactions/{id}/delete` (undo toast). Template `fragments/dialogs/edit-transaction.html` and shell page `pages/entries/open-edit.html`.

Probe: Playwright (Chromium) against the e2e live server with a scratch DB (never `data/budget.sqlite`), 1440x900, 1024x768, 375x812, light and dark (colour scheme emulation), 7 states x 6 configurations = 42 captures. Every capture waits for `dialog[open]`, kills animations and transitions, then waits 400 ms before the diagnostics are read from the DOM and the screenshot is taken. Seeded: accounts Checking (PLN), Savings (PLN), Euro (EUR), Yen (JPY); expense category Groceries, income Salary, the seeded transit; one transaction per state (35.50 PLN, 123.45 EUR, 5000 JPY, a 21.93 transit to Savings). Opened through the transaction's own URL (the plain load: the shell page asks the route for the dialog), so the ledger page itself (T-UR09a) is not part of this record.

The final visual-auditor pass runs after the merge with T-UR09a.

## Diagnostics (five signals)

States: normal (PLN), eur, jpy, transit, error (422 after saving 0), picker (search panel open), no-match (search "zoo"). Light and dark gave identical values.

| Route (state) | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /transactions/{id}/edit (7 states) | 1440 | false | 0 | 0 | 0 (1 in error, see note) | 0 |
| /transactions/{id}/edit (7 states) | 1024 | false | 0 | 0 | 0 (1 in error, see note) | 0 |
| /transactions/{id}/edit (7 states) | 375 | false | 0 | 0 | 0 (1 in error, see note) | 0 |

Note: the only console entry is the browser's "Failed to load resource: 422 (Unprocessable Entity)" line for the deliberately invalid save of the error state. No `pageerror`, no CSP violation, no htmx target error.

## Captures

Under the scratchpad `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR09b/` as `<state>__<1440|1024|375>__<light|dark>.png`, diagnostics in `diag.json`. Viewed: normal 1440 light (band, hero `-35.50` with PLN, recent chips with the checked category, search button, account, date and note, cancel and `[ save ]`), transit 375 dark (bottom sheet, arrows sign, 21.93, account next to destination, lime primary).

## Handoff comparison

Matching: band and title (`edit transaction · <category>`), hero amount with sign and currency, category field (recent chips, `search all N categories`), account row, date and note row, cancel + `[ save ]`, the transit variant (arrows sign, destination field shown), the 422 hero error, the phone sheet at 375.

Differences (all listed in `docs/plans/ui-redesign/derived.md`, T-UR09b): no delete button in the dialog (handoff has none; delete stays in the row menu and answers with the undo toast); posted field names are the route's, labels are the handoff's; the plain page load replaces the URL with `/today`. Open: at 375 the account select next to the destination is narrow (`Checki▾`), the same two-column row as the handoff transit variant.

## Behaviour contract (step 3b)

- Prefill is the service value in the account currency: 35.50 PLN, 123.45 EUR, 5000 JPY (integration tests pin the strings).
- Failing saves (empty post, amount 0, bad date, transit without or with a wrong destination) answer an HTML 422 with the summary and per-field errors, keep the posted values, write nothing (rows and audit asserted).
- Swap targets: the form posts to `#modal-root` (innerHTML); a save answers an empty body, the out-of-band `#modal-root` clear and `#flash-region` flash, `HX-Reswap: none`, the three stale events, and `HX-Refresh` off the ledger. The hero follows account and category through `GET /transactions/{id}/edit?hero=1` (only `.rd-dialog__hero` is swapped), the credit line through `/transactions/_limit_preview` with the edited id excluded.
- No arithmetic or `float` in the template; every number is the service value.

## Visual-auditor pass (frontend-visual-audit skill, head a366c2e0)

Scratch DB (never `data/budget.sqlite`), app on 127.0.0.1, Chromium, 1440x900, 1024x768, 375x812, light and dark, 7 states each (pln, eur, jpy, transit, picker, no-match, error 422) = 42 captures, plus a hero-refresh, save, forced-failure and delete pass at 1440 light. Seeded: Checking and Savings (PLN), Euro (EUR), Yen (JPY), a 35.50 PLN, 123.45 EUR, 5000 JPY expense each and a 21.93 PLN transit; cached FX rates for EUR and JPY (without them /today answers 503, ADR-0139, which is a scratch-data matter). Every capture waits for `dialog[open]`, then `document.getAnimations().length === 0`, then 150 ms. Opened by a plain load of `/transactions/{id}/edit` (the ledger is on the old shell until T-UR09a).

### Diagnostics (42 captures, all light/dark and 3 widths)

| Route (state) | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /transactions/{id}/edit (pln, eur, jpy, transit, picker, no-match, 422) | 1440 | false | 0 | 0 | 0 | 0 |
| same | 1024 | false | 0 | 0 | 0 | 0 |
| same | 375 | false | 0 | 0 | 0 | 0 |

The deliberate 422 console line is excluded (expected). Broken images 0.

### Handoff comparison (side by side with edit-transaction, --error, --transit, category-picker, --no-match, at 1440 and 375, light and dark)

Matches: band and title, hero sign and amount and currency, recent chips plus search, picker sheet at 375 (drag handle, search with esc, rows with direction), no-match panel, the 422 hero error line plus summary box, transit arrows sign, lime primary in dark, phone sheet without cancel. The handoff chip colours are absent only because the scratch categories have no colour.

Findings:
1. Layout, transit row: account and destination are not equal columns. At 1440 the account select is about 255 px and the destination about 205 px; at 375 the account shows `Checki▾` and the destination is wider. The handoff transit page has two equal columns (`Checking` in full). So the narrow account select does not match the handoff and is not accepted. Shots: `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/ur09b-audit/shots/transit__375__light.png` against `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/ur09b-audit/ref/edit-transaction--transit__375__light.png`; `transit__1440__dark.png`.
2. Layout, minor: the vertical gap from the account row to the date row is about 10 to 20 px larger than the handoff (the empty `#credit-line` placeholder keeps its margin when there is no credit line).
3. Behavior, blocking: after a successful save from /today the success flash is never visible. The 200 answer carries `HX-Reswap: none` and `HX-Refresh: true` off the ledger, so the page reloads before the out-of-band `#flash-region` swap shows; polled every 250 ms for 2 s afterwards, `#flash-region` is empty and invisible. The dialog is closed and `#modal-root` is empty, no duplicate ids. (Seen on the plain-load route that ends on /today; on the ledger the flash path is T-UR09a.) Shot: `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/ur09b-audit/shots/flash-after-save__1440__light.png`.
4. Copy, triage: the 422 line reads "amount must be positive" and the hero shows `-0` (posted text); the handoff error page shows "Enter an amount above 0.00" and `-0.00`. Not in derived.md.
5. Shared picker, triage: the no-match panel has no "+ new category" button (handoff has it); `new_category_url` is passed by no caller, so this is the shared picker, not this item.

### Behaviour contract (step 3b)

- Prefill equals the DB: amount 35.50 / 123.45 / 5000 / 21.93 for stored 3550 / 12345 / 5000 / 2193; account, date, note, category (checked radio) and the transit destination (Savings) match; JPY has no decimals.
- A save of 36.75 stored 3675 (the same pass changed the category to Salary through the picker); audit_log has an `update` row with prev 3550 and new 3675 and the new category.
- Hero refresh after the category change: sign flips from `−` to `+` (the `?hero=1` swap; targets `#modal-root .rd-dialog__hero` and `#credit-line` each match exactly once).
- Failing save (amount 0): visible hero error line plus summary box, rows, amount and audit_log count unchanged. Forced 500, 404 and 409 on the POST: each shows a visible flash ("Something went wrong on our side", "That item was not found", "That item changed in the meantime") and the dialog stays open; none looks saved.
- After the success save: `#modal-root` is empty, no `dialog[open]`, no duplicate ids; the flash is NOT visible (finding 3).
- `GET /transactions/{id}/edit` with HX-Request answers 200, `HX-Retarget: #modal-root`, `HX-Reswap: innerHTML`. `POST /transactions/{id}/delete` answers 200 with `HX-Reswap: delete`, the three stale events and the "transaction deleted" undo toast; the row is soft-deleted with a `delete` audit row, and the edit route then 404s.
- Template grep (edit-transaction.html, open-edit.html): no `float`, `/ 100`, `* 100`, arithmetic, `{% set` or `style=`.
- Swap targets: every `hx-target` on the open dialog matches exactly one element.

Captures: `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/ur09b-audit/shots/<state>__<1440|1024|375>__<light|dark>.png` (viewed: pln 1440 light, transit 375 light, transit 1440 dark, picker 375 dark, error 375 light, no-match 1440 light), handoff renders in `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/ur09b-audit/ref/`; data in `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/ur09b-audit/rows.json`.

## Re-audit after fixes (head 468e7051, visual-auditor)

Scratch DB with Checking, Savings, Euro, Yen and a liability account Card (credit limit 5000.00); 1440, 1024, 375, light and dark; states: /today, transit, expense without liability, expense on the liability account, 422; then a save on /today at 1440 light. Captures `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/ur09b-audit/shots/re-<state>__<vp>__<scheme>.png`, data `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/ur09b-audit/re.log`.

### Diagnostics

| Route (state) | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /today | 1440, 1024 | false | 0 | 0 | 0 | 0 |
| /today | 375 | false | 1 (pre-existing, see below) | 0 | 0 | 0 |
| edit: transit, no liability, liability, 422 | 1440, 1024, 375 | false | 0 | 0 | 0 | 0 |

Light and dark are identical. The one overflowing element at /today 375 is the decorative `pre.rd-hero__loaf` (aria-hidden, right edge 399 against 375, clipped by the hero, no horizontal scroll). Its template and the CSS are byte-identical on `ui/sourdough` (`git diff ui/sourdough 468e7051 -- src/budget_planner/web/static` is empty; the `<pre>` is in the hero on both), so it is pre-existing on MAIN, not caused by the refresher.

### Re-check of the findings

1. F1 fixed. Transit row: account and destination are 230 px each at 1440 and 1024 and 160 px each at 375; the account select reads `Checking` in full and is not clipped (scrollWidth equals clientWidth); matches the handoff's two equal columns (`re-transit__375__light.png`).
2. F2 fixed. Account select bottom to date input top: 63 px with no credit line at every width (the previous build showed an empty placeholder). With the liability account the credit line renders ("Card · 4,800.00 of 5,000.00 left → 4,790.00 after this") and the gap is 81 px at 1440 and 1024, 99 px at 375 (the line wraps), as in the handoff where the line takes its own room.
3. F3 fixed. Save on /today: `transaction saved` flash visible and stays visible (#flash-region polled 4 x 250 ms), no page navigation (`beforeunload` 0), dialog closed, `#modal-root` empty. Network after the POST: exactly one `GET /today` (the hidden refresher) plus the upcoming list refetches, which is accepted. Net worth refreshed from 7,390.00 to 7,370.00 after the amount went 50.00 to 70.00 (assets 7,600.00 to 7,580.00). No duplicate ids after the out-of-band swap; focus falls to `body` (the dialog was removed) and scrollY stays 0, no jump. Stored amount is exact (5000 after saving 50.00). The hidden refresher measures 0 x 0 with `display: none`, no margin: no layout gap.
4. F4 fixed. The 422 hero input shows `0.00` (hero `−`, "amount must be positive" summary unchanged; copy difference remains triaged).
5. Today regression: see the table; no layout gap, no new overflow.

Template re-grep (edit-transaction.html, field.html, hero.html, today/index.html): no new arithmetic, `float`, `{% set` or `style=` introduced by the fixes (the diff shows only id attributes, the hidden refresher and conditional blocks).
