# Frontend audit: T-UR12, Plan forecast and analytics tabs on the new shell

- Branch: wi/ui/sourdough/UR12, audited head 52b4f3b3. Date: 2026-11-25. Role: visual-auditor (frontend-visual-audit skill, Steps 1 to 6).
- Data: scratch copy of data/demo.sqlite (migrated, login user seeded) and a fresh empty scratch DB. Never data/budget.sqlite. Servers on 127.0.0.1:8101 (demo) and :8102 (empty), BUDGET_ENV=dev, session minted directly.
- Reference: docs/design/rising-dough-frontend/pages/plan/forecast.html, pages/plan/analytics.html, charts/*.html (rendered with ?theme=light|dark at 1440 and 375).
- Supersedes the implementer's throwaway probe record (same file); the probe's findings are folded in.

## Routes and states

Each state at 1440, 1024 and 375, light and dark. Every HTMX state was reached by clicking the button and waiting until the pressed button flipped and the row count or hero changed, plus 500 ms.

| Route | Demo DB states | Empty DB states |
|---|---|---|
| /plan?tab=forecast | default (12), 6, 12, 24, 60 | default (12), 6, 24, 60 |
| /plan?tab=analytics | default (month), year to date, 12 months | default (month), year to date, 12 months |

96 captures (4 route/DB groups x 2 themes x 3 viewports x 3 to 5 states).

## Diagnostics

All 96 captures: horizontalScroll=false, overflowingElements=0, duplicateIds=0, consoleErrors=0, requestFailures=0, HTTP status >= 400 = 0, broken images = 0, exactly one #main.

overflowingElements counts descendants whose right edge passes the viewport and that are NOT inside a scroll container (overflow-x auto/scroll/hidden/clip). At 375 the forecast chart SVG (viewBox 1184 wide) and the wide tables are wider than the viewport on purpose; they sit inside scroll regions (tables: role=region, tabindex=0, "Table (scrolls sideways)"), so the page itself never scrolls sideways.

| Group | 1440 L | 1440 D | 1024 L | 1024 D | 375 L | 375 D |
|---|---|---|---|---|---|---|
| forecast demo (5 states) | 0 | 0 | 0 | 0 | 0 | 0 |
| forecast empty (4 states) | 0 | 0 | 0 | 0 | 0 | 0 |
| analytics demo (3 states) | 0 | 0 | 0 | 0 | 0 | 0 |
| analytics empty (3 states) | 0 | 0 | 0 | 0 | 0 | 0 |

"0" = all five signals zero/false in every state of the group.

## Screenshots viewed (scratchpad shots/, /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/shots/)

Viewed: fc-demo__1440__light__default, an-demo__1440__dark__12_months, an-demo__1440__dark__default, fc-demo__375__dark__60, an-empty__375__light__default, tooltip-fc-1440, an-back-stale-1440, and board-forecast-1440-light, board-analytics-1440-dark. Others are captured with the same diagnostic and were not all opened.

## Board comparison

Matches the board: hero (label, wide figure, PLN unit, note), tab pills, horizon segmented control and caption, chart card caption, gridlines and tick labels, x labels with year sub-labels, line, area, white dots, hover guide line plus tooltip ("JAN 2027 . END OF MONTH, value, net"; tooltip shown on hover, verified), table header, row rhythm, ▲ mark and pink on negative net, analytics two-column layout, spend rows with 20-cell bar, income-vs-expense loaves with legend, largest-items card, dark theme (orange hero, lime accent, dark cards), empty states.
Accepted (confirm only): chart shape and gridline count differ where demo data differs from the board (demo forecast peaks at 34,682 with gridlines -20k to 40k; board 20k to 100k; demo has more income/expense months than the board's four); derived.md deviations (horizon buttons reload #main, thinned x labels at 60 months, analytics period query names, picker note, chip link, bar minimum cell).
Observation, not UR12: category chips are neutral grey on the demo DB where the board tints them. The demo categories carry arbitrary hex colours that the category_color filter maps to no palette name; same filter as the budget tab.

## Step 3b

1. Swap targets: every hx-target / hx-select is #main; count is 1 before and after every swap in all 96 captures. ok.
2. Failing saves: no state-changing form on either page (GET buttons only). n/a. A failing GET swap was not forced.
3. Templates (forecast.html, analytics.html, _tabs.html, charts/forecast.html, charts/income-vs-expense.html, charts/tooltip.html, rows/forecast-month.html, rows/analytics-category.html, plan/period-nav.html): rg finds no style=, no {% set %}, no float, no / 100 or * 100, no literal currency code; no arithmetic inside {{ }}. Only layout constants copied from the board stay literal in the chart SVG (x=56, y=268/286/302, r=5/18). ok.
4. Money by currency: cells use money_num(base_ccy) or precomputed text; only base currency PLN exists on the scratch DB, JPY/non-PLN not exercised on these pages (base-currency aggregates only).
5. Rendered equals service (demo DB, calling forecast.monthly_projection, analytics.bundle, spend_total_minor, format_money): forecast row count and every Balance (EOM) cell equal the projection for horizons 6, 12, 24, 60; analytics hero equals spend_total_minor for month (22,862.28), year to date (97,045.03), 12 months (97,045.03); the sum of the period column equals the hero in all three. ok.
6. IDs and listeners: duplicateIds=0 after every swap; no HX-Trigger on these GETs. ok.
7. URL: horizon click pushes /plan?tab=forecast&horizon=N; range click pushes ...&period=year|trailing-12&year=&month=. Pressed button and rows follow the click. ok.
8. U+2212: hero note, net column, tooltips, aria-labels use U+2212. FAIL for the Balance (EOM) cells and the chart y tick (see findings).
9. Back/forward: URL and content restore, aria-pressed does not (see findings).

## Findings

1. Behavior, back/forward leaves the wrong button pressed (forecast and analytics). After clicking 6, 12, 24 and pressing back, URL is horizon=12 and 12 rows show, but the pressed button is 24 (back to horizon=6: pressed 12; analytics back to period=year: pressed "12 months"). Cause: static/rd/js/segmented.js flips aria-pressed on click before htmx saves its history snapshot, so the snapshot of the previous URL holds the next button as pressed. Fix: do not flip aria-pressed in segmented.js for buttons with hx-get (let the swapped #main set it), or set htmx.config.historyCacheSize=0 / refetch on restore for these pages. Screenshot: /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/shots/an-back-stale-1440.png. Blocking (wrong state shown, a11y state wrong).
2. Template logic / sign, ASCII hyphen-minus in negative Balance (EOM) cells and in the chart y-axis tick. Rendered "-18,830.45 PLN" (money_num) and tick "-20,000" while the net column, tooltip, hero and aria-labels print U+2212 and the board uses U+2212. Same row mixes both signs. Fix: view-model text from domain.money.format_figure for end balance (as net_text does) and a U+2212 axis formatter in chart_geometry.format_axis_number. Files: fragments/rows/forecast-month.html (end_balance cell), web/chart_geometry.py. Blocking per brief (U+2212 signs).
3. Note (not blocking): forecast chart at 375 shows only about 9 of 12 months before the card edge and relies on sideways scroll of the SVG container; check the chart card is keyboard-scrollable (points are focusable, so focus scrolls them into view).

## Result

FINDINGS: diagnostics all 0; two Step 3b/behaviour findings above go back to the implementer.
