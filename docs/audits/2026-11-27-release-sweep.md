# Pre-release visual sweep (T-UR16 validation), item SWEEP

- Commit audited: `e85b245e` (ui/sourdough tip at start; detached worktree). Scratch DB: migrated copy of `data/demo.sqlite` (never `data/budget.sqlite`). App: uvicorn, `BUDGET_ENV=dev`, Chromium via Playwright; diagnostics are `DIAGNOSTIC_JS` from `scripts/audit_frontend.py`, driver in the scratchpad (login added).
- Viewports 320 / 375 / 768 / 1024 / 1440 / 1920, light and dark (`color_scheme`), 288 page loads (21 routes x 6 x 2 + admin pages). Screenshots (full page): `<scratchpad>/shots/{light,dark}_<w>_<route>.png`, `adm_*` for admin pages, `3b_*` for the dialog checks. Viewed: today 320/1920 light, plan 375 dark, ledger 768 light, login 320 dark, dialogs (new entry 500, account 404).

## Routes

Authenticated (owner): /today, /ledger, /ledger/recently-deleted, /plan, /plan?tab=year (alias /budget/yearly), /budget, /forecast, /accounts, /settings, /settings/password, /settings/security, /auth/sessions (the last four redirect into /settings/security), /add?when=happened (redirects to /today with the dialog), /transactions (redirects to /ledger?view=actual).
Admin (user 2): /settings/users, /settings/users/new, /settings/users/invites/new (404 for a non-admin, expected).
Anonymous: /auth/login, /auth/register (redirects to login), /setup (redirects to login: setup closed on this DB), /invite/sweeptoken (error page).
Not swept as pages: ledger `?view=planned` and `?view=recurring` (only opened for the Step 3b dialogs), settings sub-pages beyond the list (no further routes exist).

## Diagnostics

Cells are horizontalScroll / overflowingElements (worst of light and dark) / duplicateIds / consoleErrors / requestFailures, summed over both themes where a count.

| route | 320 | 375 | 768 | 1024 | 1440 | 1920 |
|---|---|---|---|---|---|---|
| /today | 0/1/0/0/0 | 0/1/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /ledger | 0/1/0/0/0 | 0/1/0/0/0 | 0/20/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /ledger/recently-deleted | 0/0/0/0/0 | 0/0/0/0/0 | 0/20/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /plan | 0/1/0/0/0 | 0/0/0/0/0 | 0/20/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /plan?tab=year | 0/20/0/0/0 | 0/20/0/0/0 | 0/20/0/0/0 | 0/20/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /budget | 0/1/0/0/0 | 0/0/0/0/0 | 0/20/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /budget/yearly | 0/20/0/0/0 | 0/20/0/0/0 | 0/20/0/0/0 | 0/20/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /forecast | 0/20/0/0/0 | 0/20/0/0/0 | 0/20/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /accounts | 0/0/0/0/0 | 0/0/0/0/0 | 0/20/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /settings | 0/2/0/0/0 | 0/2/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /settings/users | 0/3/0/2/0 | 0/3/0/2/0 | 0/10/0/2/0 | 0/0/0/2/0 | 0/0/0/2/0 | 0/0/0/2/0 |
| /settings/password | 0/2/0/0/0 | 0/2/0/0/0 | 0/15/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /settings/security | 0/2/0/0/0 | 0/2/0/0/0 | 0/15/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /auth/sessions | 0/2/0/0/0 | 0/2/0/0/0 | 0/15/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /settings/users/invites/new | 0/0/0/2/0 | 0/0/0/2/0 | 0/0/0/2/0 | 0/0/0/2/0 | 0/0/0/2/0 | 0/0/0/2/0 |
| /add?when=happened | 0/1/0/0/0 | 0/1/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /transactions | 0/1/0/0/0 | 0/1/0/0/0 | 0/20/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /auth/login | 0/1/0/0/0 | 0/1/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /auth/register | 0/1/0/0/0 | 0/1/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /setup | 0/1/0/0/0 | 0/1/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /invite/sweeptoken | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /settings/users/new | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |

Totals over 288 loads: horizontalScroll=0, duplicateIds=0, requestFailures=0, consoleErrors=24, all of them the 404 page for /settings/users and /settings/users/invites/new when loaded as the non-admin owner (rows above); the same routes loaded as admin: 0 console errors, 0 failures.

### overflowingElements breakdown (none produces horizontal scroll)

- Known/pre-existing, not re-investigated: `pre.rd-hero__loaf` on /today 375 and 320; `a.rd-tabs__tab` inside the `overflow-x:auto` tab strip at 375/320 (ledger, plan, settings, forecast, transactions); year cells inside the plan year scroll region (/plan?tab=year, /budget/yearly at 320 to 1024). Ledger filter row at 1024: no overflow signal in this run (LEDGERPH fix in flight on another branch).
- New, same class as the known ones: decorative `pre.rd-auth__loaf` on /auth/login, /auth/register, /setup at 320 and 375 (clipped art, `rd-auth__loaf` ends past the viewport; it also overlaps the end of the "Hello again." heading at 320, see finding 2); `label.rd-chip-option` in the new-entry chip row at 320/375 (/add); forecast chart `svg`/`line` at 320/375 (chart wider than its container, no scroll).
- At 768: wide tables (ledger, planned/deleted, budget, forecast, accounts, sessions, users) are 760 to 948 px inside `.rd-table-scroll` (`overflow-x:auto`, panel 672 px). No page scroll, columns are reachable by scrolling the region, but the amount column starts cut at the right edge (header "AM", day net "NE" visible in `ledger` 768 screenshot). See finding 1.

## Step 3b (behaviour contract)

Run at 1440 on the scratch DB, one save per main dialog:

- Swap targets: every non-relative `hx-target` on /today, /ledger?view=planned, /plan, /accounts matches exactly one element (bad=[]); no duplicate ids on those pages, after opening the dialog, or after the successful save.
- Forced failing saves (`page.route` fulfilling the POST with 404 / 409 / 500): new entry, edit planned, edit budget (override dialog) and new account each keep the dialog open and show a visible message ("That item was not found...", "That item changed in the meantime...", "Something went wrong on our side. Try again."). The message appears twice in the DOM text (toast plus dialog flash, both visible); not blocking, see finding 3. The 24 console "Failed to load resource" lines in this step are the forced statuses.
- Real saves: new entry ("Transaction saved"), edit planned ("Planned entry saved"), edit budget ("Big Purchases budget saved") closed the dialog and flashed. New account: a duplicate name returned the visible 422 message "An account with this name already exists" (an earlier attempt had created the row); the dialog stayed open with the error.
- Browser-native `required` validation blocks an empty new-entry/new-account submit with a tooltip (no request); the account currency combobox starts empty.
- Templates: `rg` over `web/templates` for `float`, `/ 100`, `* 100`, arithmetic `set` blocks: 0 hits; `tests/architecture/test_template_logic.py`: 2 passed.
- Rendered numbers: planned "Car" amount in the edit dialog (2,239.80) equals the Upcoming row on /today (-2,239.80); net worth 34,439.69 matches between /today and /accounts. A direct service call comparison was not run (timebox).

## GitHub results (ui/sourdough)

`e85b245e` runs were cancelled when `22af385b` was pushed (e2e, a11y-perf, Visual cancelled; Security, Terraform, Lock check passed); `22af385b` runs were still in progress at read time. Nearest completed tip `3b360a20` (parent of the FORMULA merge):

- e2e: Chromium success (278 passed, 4 skipped), firefox advisory success (3 passed, 279 skipped, i.e. mostly skipped by design), webkit advisory success (272 passed, 4 skipped, 6 xfailed).
- a11y (axe, 1440, 9 of 11 routes; /auth/sessions and /settings/password are redirects): 0 serious/critical. Moderate: `landmark-unique` on `.rd-hero` at /settings, /settings/security, /settings/users (1 node each).
- Lighthouse (9 routes x 3 runs): all budget assertions passed ("All results processed"); per-category scores are not printed in the job log (stored in the uploaded artifact).
- CI (`just ci`) failed: tests/contract/test_route_coverage.py (uncovered route `/categories/picker`), tests/integration/web/test_budget.py:170, tests/ui_map/test_mockup_{entries,settings,today}.py (UI-map assertions: PICKNEW/FORMULA era mockup mapping), plus the four shifted-clock pytest jobs. Visual failed: the 6 advisory handoff reference comparison jobs (e.g. /ledger?view=recurring 1440 dark 0.37% differ vs 0.10% max) and the pinned visual suite / visual-gate. These are not browser findings from this sweep; the orchestrator should re-read them on the final tip.

## Findings

1. minor: /ledger, /ledger/recently-deleted, /plan, /forecast, /accounts, /settings/security (sessions) at 768: tables are wider than the panel (760 to 948 px vs 672 px) inside a scroll region, so the amount column is cut at the right edge until the user scrolls (`ledger` light/dark 768). No page scroll, text reachable. Fix idea: collapse a column or use the 375 card layout up to 768.
2. minor: /auth/login (and /auth/register, /setup) at 320: the decorative `pre.rd-auth__loaf` overlaps the end of the "Hello again." heading and runs past the viewport edge (`dark_320_auth_login.png`); readable but touching. Same class as the known /today loaf.
3. minor: failing-save messages are rendered twice (two visible elements with identical text) in the dialog flow (toast and dialog flash); verify this is intended.
4. minor/info: /forecast chart svg (320, 375) and new-entry chip row (320, 375) exceed the container with no scroll; not visually broken in the screenshots checked, only counted by the diagnostic.
5. info: moderate axe `landmark-unique` on `.rd-hero` (settings pages), see GitHub results.

No blocking finding in the browser sweep (0 horizontal scroll, 0 duplicate ids, 0 request failures, 0 unexplained console errors, every forced failing save visible).
