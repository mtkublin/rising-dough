# Frontend audit: T-UR12, Plan forecast and analytics tabs on the new shell

- Branch: wi/ui/sourdough/UR12. Date: 2026-11-25.
- Method: Playwright (chromium) probe over the e2e live server on a scratch DB (never data/budget.sqlite), one PLN account with 5,000.00, no transactions. The probe script was throwaway and is not committed. The orchestrator's visual-auditor re-runs the skill on this branch afterwards; this record holds the probe's numbers.
- Reference: docs/design/rising-dough-frontend/pages/plan/forecast.html, pages/plan/analytics.html, charts/forecast.html, charts/income-vs-expense.html.

## Routes and states

Each route at 1440, 1024 and 375, light and dark (6 runs per route):
/plan?tab=forecast (12 months), /plan?tab=forecast&horizon=6, /plan?tab=forecast&horizon=60 (long range), /plan?tab=analytics (empty month), /plan?tab=analytics&period=trailing-12.

## Diagnostics

30 runs. In every run horizontalScroll=false, overflowingElements=0, duplicateIds=0, consoleErrors=0, requestFailures=0 (also no HTTP >= 400).

| Route / state | 1440 light | 1440 dark | 1024 light | 1024 dark | 375 light | 375 dark |
|---|---|---|---|---|---|---|
| forecast 12 | 0 | 0 | 0 | 0 | 0 | 0 |
| forecast 6 | 0 | 0 | 0 | 0 | 0 | 0 |
| forecast 60 | 0 | 0 | 0 | 0 | 0 | 0 |
| analytics empty | 0 | 0 | 0 | 0 | 0 | 0 |
| analytics 12 months | 0 | 0 | 0 | 0 | 0 | 0 |

"0" means all five signals are zero/false.

## Screenshots viewed (scratchpad UR12/shots/)

forecast-1440-light, forecast-60-1440-dark (60 months: labels thinned to every third month, all ticks kept), analytics-empty-375-light. Checked: hero, tabs, horizon segmented control, chart card, table, empty states, light and dark contrast.

## Step 3b

1. Swap targets: the horizon and range buttons use hx-target/hx-select `#main` (one element before and after; verified by the e2e journeys that click 24 months and 12 months and read the URL, pressed button and row count).
2. No state-changing form on either page.
3. Templates: no style=, no {% set %}, no float, no / 100, * 100; comparisons only choose wording or classes.
4. Money: table cells, heroes and deltas print precomputed view-model text or money_num(base_ccy); chart text is built in web/chart_geometry.py from domain.money.
5. Rendered equals service: tests/integration/web/test_plan.py and test_plan_analytics.py assert exact amounts, month labels, point counts and deltas against the service values (for example Groceries 200.00, 12-month average 25.00, delta +175.00).
6. Scratch data only.

## Result

CLEAN on the probe: all five diagnostics 0. Open (not a template defect): visual parity with the handoff references needs seed data the base seed lacks (see derived.md and the item report): the seed's forecast series reaches 58,761.15 (4 gridlines) where the board has 86,239.67 (5 gridlines), and the seed has one month of income and expense history where the board draws four.
