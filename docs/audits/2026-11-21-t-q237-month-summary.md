# Frontend audit: T-Q237 budget numbers come from the view model

Change: T-Q237 (Q-039, ADR-0130 D3, ADR-0138). Templates `today/index.html`, `today/_upcoming.html`,
`plan/*`, `budget/index.html`, `budget/_yearly.html`, `partials/budget/_override_form.html` and
`partials/forecast/*` now render values precomputed in `web/view_models.py` (left per day, spent and
committed percent, remaining after spend, per-row used percent, over/under flags, month pickers, year
tab rows, upcoming groups, analytics spend rows). Named date filters replace `strftime` patterns and
chart objects expose `plot_right` / `x_label_y`. No CSS edited.

Run: `frontend-visual-audit` approach (headless Chromium via Playwright), app on a migrated scratch copy of
`data/demo.sqlite` at `/tmp/t-q237.sqlite` (never `data/budget.sqlite`), logged in through a minted session.
Screenshots: `/tmp/fe-audit-t-q237/<viewport>_<route>.png`; viewed `1440__today.png` (hero, bar, legend,
net worth, upcoming groups) and `375__plan_tab_budget.png` (period bar, per-day figure, category table).

## Routes and diagnostics

Routes (each at 1440, 1024 and 375; 33 runs): `/today`, `/today/upcoming`, `/plan?tab=budget` (current),
`/plan?tab=budget&year=2026&month=8` (past), `/plan?tab=budget&year=2027&month=3` (future), `/plan?tab=year`,
`/plan?tab=forecast`, `/plan?tab=analytics`, `/budget`, `/budget/yearly`,
`/budget/rules/1/overrides/new?inline=1&month=3&year=2027`.

| Diagnostic | Result |
|---|---|
| horizontalScroll | false for every full page at all viewports. `true` only for the bare fragment `/budget/yearly` (unstyled HTMX fragment fetched directly, never a page; identical markup width to before) |
| overflowingElements (outside `.rd-table-scroll` / `.ledger-scroll`) | 0 everywhere except `/plan?tab=analytics` at 375 (71 descendants, page-level scroll stays false; pre-existing, same as the T-Q252 record, layout untouched) |
| duplicateIds | 0 everywhere |
| consoleErrors | 0 everywhere |
| requestFailures | 0 everywhere |
| `-0.00` / `NaN` / `None` / `Traceback` in visible text | none |

All 33 responses were HTTP 200.

## Step 3b

1. Swap targets: no `hx-target` / `hx-swap` attribute edited; `#upcoming-root`, `#plan-budget`,
   `#budget-row-*`, `#override-slot-*` ids unchanged, no duplicate ids.
2. No state-changing form touched (override form only changed where its month/year labels come from).
3. No arithmetic in templates: `tests/architecture/test_template_logic.py` is green with the 37 entries for
   `today`, `plan`, `budget`, `partials/budget`, `partials/forecast` deleted (zero `{% set %}`, `float`,
   scaling, arithmetic or `strftime` in those templates).
4. Money formatting: unchanged filters (`money`, `money_num`, `money_whole`) with `base_ccy`.
5. Rendered equals service: Today hero and Plan period bar both read `-17.00` for the same fiscal month;
   `tests/integration/web/test_budget_view_values.py` asserts hero per-day, period-bar per-day, row
   planned/actual/remaining, 25 percent bar widths on Today, Plan and Budget against
   `view_models.left_per_day` / the service summary.
6. IDs and listeners: unchanged events; no new `HX-Trigger`.
7. Scratch data only: yes (`/tmp/t-q237.sqlite`, deleted afterwards).
