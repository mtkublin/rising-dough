# Frontend audit: Plan unbudgeted list (PLANCAT)

Date: 2026-11-27. Item PLANCAT, branch wi/ui/sourdough/PLANCAT, audited sha 451134c4. Tasks T-UR75 (R14), T-UR80 (R20).
Run with the frontend-visual-audit skill (Playwright, Chromium) against a scratch copy of data/demo.sqlite (migrated, login user seeded), env=dev, 127.0.0.1:8137. data/budget.sqlite untouched. Scratch data: November 2026 transactions added (Taxes 123.45, Bank Fees #18 25.00, Groceries 199.75, Car 300.00); Taxes, Fixed Costs, Bank Fees #18, Takeaway had no budget (Taxes and Bank Fees #18 with ledger records, Fixed Costs and Takeaway without); 3 archived categories (Bank Fees, Bank Fees #17, VAT Refund #6). MAIN (ui/sourdough e2b3d292) run on a copy of the same DB for the year-tab comparison.

Routes: /plan?tab=budget&year=2026&month=11, /plan?tab=year&year=2026. Viewports 1440, 1024, 375, each in light and dark (prefers-color-scheme). Driver and per-step JSON/PNG in the scratchpad (see Screenshots).

## Diagnostics

Columns: horizontalScroll / overflowingElements / duplicateIds / consoleErrors / requestFailures. Identical in light and dark.

| Route / step | 1440 | 1024 | 375 |
|---|---|---|---|
| budget, collapsed | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| budget, list expanded | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 (layout finding F1) |
| budget, set budget dialog open | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| budget, after save (row moved, flash) | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| year, collapsed | false/0/0/0/0 | false/10/0/0/0 (a) | false/10/0/0/0 (a) |
| year, list expanded | false/0/0/0/0 | false/10/0/0/0 (a) | false/10/0/0/0 (a) |
| year, after clicking an archived link (F2) | false/0/0/1/1 | false/10/0/1/1 | false/10/0/1/1 |
| year, link dialog (Fixed Costs) | false/0/0/1/1 (b) | false/10/0/1/1 (a, b) | false/10/0/1/1 (a, b) |

Notes:
- (a) The overflowing elements are table.rd-year and its children inside the sideways-scrolling year grid; same 10 elements and right edges (1198 at 1024, 1182 at 375) on MAIN. Pre-existing; page has no horizontal scroll.
- (b) The one console error and request failure are the 404 of GET /budget/rules/25/overrides/new (archived category link, F2), carried over from the earlier click in the same session. The dialog for a live category loads with 200.
- The forced 404/409/500 run at 1440 light adds 3 console errors ("Failed to load resource") on the budget page; they are the forced responses, expected.

## Behaviour

- Budget tab: 12 budgeted rows in the main table; collapsed summary "4 categories without a budget"; live unbudgeted expense categories in the scratch DB = 4 (Bank Fees #18, Fixed Costs, Takeaway, Taxes), archived ones absent. The second table is hidden while collapsed. Expanded: the four rows with spent (25.00, 0.00, 0.00, 123.45), "no budget" and a "set budget" button in the STATUS cell.
- Set budget on Taxes (500.00, default tier): dialog titled "set budget · Taxes", save closes it, flash "Taxes budget saved", Taxes row now in the main table (123.45 / 500.00, left 376.55), heading becomes "3 categories without a budget". All viewports and themes.
- Keyboard: Enter on the focused summary opens, Space closes, Space opens; focus stays on the summary; next Tab goes to the table scroll region, then the buttons; summary focus outline solid 2px.
- Year tab: grid has budgeted rows only (Taxes appears after it got a budget); collapsed "5 categories without a budget" with 5 links, each hx-get to /budget/rules/<id>/overrides/new?...&tier=default. Live link (Fixed Costs) opens "set budget · Fixed Costs".
- Column alignment (budget tab, expanded): the second table has no header and sits inside the disclosure padding, so its columns are offset from the main table (1440: STATUS column starts at 1069 vs 1170; bar column 331 vs 314). Readable, no overflow at 1440/1024; "no budget" text stacks above the button in the status cell.

## Findings

- F1 (Layout, blocking) /plan?tab=budget, list expanded @ 375: the card layout of the second table is broken. Category chips are squashed to circles ("BANK FEES #18" wrapped in 54 px), the "no budget" text overlaps the chip, the bar column is 19 px wide (cells measured: category 54, bar 19, spent 65, status 198). The main table at the same width renders as clean cards. The status cell also pushes the "set budget" button to the right of the text rather than below. Screenshots: shots/375-light__02-budget-expanded.png, shots/375-dark__02-budget-expanded.png. Fix: the second table needs the same mobile card rules as the main table (it lacks the head row / modifier the card layout keys on), or the status cell must not be inline-flex at that width.
- F2 (Behavior/Content, blocking) /plan?tab=year, list expanded, all viewports: the disclosure lists archived expense categories ("Bank Fees", "Bank Fees #17": count 5 instead of the 3 live ones). Clicking one fires GET /budget/rules/25/overrides/new -> 404 and nothing visible happens (no dialog, no flash; console 404). Cause: `year_page` now takes every row with `total_minor == 0` from `budget_service.yearly_budgets` (which includes archived categories), where MAIN filtered them out via usage. The budget tab correctly excludes them. Fix: restrict the year disclosure to live categories (same live-expense selection as the budget tab).
- Minor (not blocking): column alignment between the two tables (see Behaviour).

## Step 3b

1. Swap targets: #modal-root count 1 before and after the dialog swap; the budget-stale reload target #main unchanged.
2. Failing saves visible: POST /budget/rules/4/overrides forced to 404, 409 and 500 from the open dialog (1440 light): the dialog stays open with "That item was not found. It may have been removed.", "That item changed in the meantime. Reload and try again." and "Something went wrong on our side. Try again." respectively. The archived-link GET 404 (F2) is silent: blocking.
3. No arithmetic in templates: the template diff adds no float, / 100, * 100 or set block (grep rc 1). The list heading is built in the view model.
4. Money formatting: not changed by the diff (rows reuse the money_num filter); JPY not re-checked.
5. Rendered numbers equal DB sums (November, minor units): Groceries page 199.75 = 19975, Car 300.00 = 30000, Taxes (second table) 123.45 = 12345. All 6 runs.
6. Duplicate ids: 0 on every page and after the swap; popover/menu ids derive from the category id and the second table has no row menus (unbudgeted rows have none). No HX-Trigger emitters or listeners added by the diff.
7. Scratch data only.

## Screenshots

Viewed: budget expanded at 1440 light, 1024 dark and 375 light; year expanded at 1440 light. Others captured and read via JSON. Directory: /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/PLANCAT/shots (<viewport>-<theme>__01-budget-collapsed, 02-budget-expanded, 03-set-budget-dialog, 04-after-save, 05-year-collapsed, 06-year-expanded, 07-year-dialog); notes in /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/PLANCAT/out.txt and out-375d.txt.

## Re-check (09d2cc79)

Date: 2026-11-27, sha 09d2cc79, same scratch DB setup (Taxes, Fixed Costs, Bank Fees #18, Takeaway unbudgeted; archived Bank Fees, Bank Fees #17), 127.0.0.1:8137, Chromium, 1440/1024/375 x light/dark. Driver: scratchpad PLANCAT/recheck.py; log rc.log; screenshots in /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/PLANCAT/shots2 (<viewport>-<theme>__<step>.png).

Routes: /plan?tab=budget&year=2026&month=11 (collapsed, expanded, set budget Taxes), /plan?tab=year&year=2026 (current), year=2025 (past), year=2027 (future); every disclosure link clicked in every year.

### Diagnostics (horizontalScroll / overflowingElements / duplicateIds / consoleErrors / requestFailures, identical in light and dark)

| Route / step | 1440 | 1024 | 375 |
|---|---|---|---|
| budget collapsed | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| budget expanded | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| budget after save | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| year 2026 expanded | false/0/0/0/0 | false/10/0/0/0 (a) | false/10/0/0/0 (a) |
| year 2026 link dialog | false/0/0/0/0 | false/10/0/0/0 (a) | false/10/0/0/0 (a) |
| year 2025 expanded (before clicking links) | false/0/0/0/0 | false/10/0/0/0 (a) | false/10/0/0/0 (a) |
| year 2025 after clicking its archived links (F3) | 2 console / 2 request failures (404) | same | same |

(a) table.rd-year inside the sideways-scrolling year grid, same 10 elements as MAIN (pre-existing, page has no horizontal scroll). Year 2027 rows show the F3 404s only because errors accumulate in the same page session.

### F1 (375 second-table cards): FIXED
Unbudgeted row is display:grid at 375: chip 118x25 (was squashed to 54 px), bar 257 wide (was 19), spent right of the bar, status cell 309 wide on its own row under the bar (top 786 vs bar 757), "set budget" button below "no budget" at the card edge. Light and dark viewed (375-dark__02-budget-expanded.png). No overlap.

### F2 (archived in the year disclosure, current year): FIXED
Year 2026: "3 categories without a budget" (Bank Fees #18, Fixed Costs, Takeaway; Taxes got a budget in the same run, so it is absent), archived Bank Fees and Bank Fees #17 absent. All 3 links return 200 and open "set budget · <name>". Same at all viewports and themes. Future year 2027: same 3, all links 200.

### Minor (column alignment): partly fixed, not blocking
rd-disclosure--table makes the list fill the panel (1440: disclosure 104/1232, second table 105/1230, main table 104/1232; 1024: 48/928 vs 49/926; 375: 32/311 vs 33/309). Category and bar columns now line up within 1 px (1440: 118 / 314 vs 315). The spent and status columns still start at different x (1440: spent 965 vs 995, status 1170 vs 1085) because the second table has narrower spent and wider status columns; readable, no overflow.

### F3 (Behavior/Content, blocking): past year lists archived categories whose links 404 silently
/plan?tab=year&year=2025, list expanded, all viewports: the disclosure shows 5 ("Bank Fees", "Bank Fees #17", "Bank Fees #18", "Fixed Costs", "Takeaway"). Archived Bank Fees (rule 23) and Bank Fees #17 (rule 25) are listed (budgeted-until-archive-month rule, ADR-0136) but GET /budget/rules/23|25/overrides/new?year=2025... returns 404: no dialog, no flash, console 404, request failure. Live links in 2025 return 200. Screenshot: shots2/1440-light__06-year2025-expanded.png. Fix: the year disclosure must not offer links for archived categories in any year (omit them, or render them as non-links), or the dialog route must accept archived categories for past periods.

### Sanity: set budget from the expanded list
Taxes 500.00 saved at all 6 combos: dialog closes, flash "Taxes budget saved", Taxes leaves the second table, heading "3 categories without a budget", Taxes row in the main table. No duplicate ids, no console errors on the budget tab.

### Step 3b (re-check)
Template diff unchanged in nature (no float, / 100, * 100, set blocks); counts come from the view model. Rendered counts equal the number of links in each year (3 / 5 / 3). Swap targets and failing-save behaviour unchanged from the first audit, except F3 (silent 404 on archived link in past years: blocking).

### Verdict
FINDINGS: F1, F2 fixed; minor alignment partly fixed (non-blocking); F3 open (blocking).

## Re-check 2 (9d98352e)

Scratch DB, light theme, 1440 / 1024 / 375 (screenshots in /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/PLANCAT/shots2, rc3-*.log).

| Route | 1440 | 1024 | 375 |
|---|---|---|---|
| budget collapsed / expanded / after save (set Taxes) | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| year 2025 expanded + 3 links | false/0/0/0/0 | false/10/0/0/0 (a) | false/10/0/0/0 (a) |
| year 2026 expanded + 3 links | false/0/0/0/0 | false/10/0/0/0 (a) | false/10/0/0/0 (a) |
| year 2027 expanded + 3 links | false/0/0/0/0 | false/10/0/0/0 (a) | false/10/0/0/0 (a) |

Cells are horizontalScroll/overflowingElements/duplicateIds/consoleErrors/requestFailures. (a) table.rd-year inside the sideways-scrolling year grid: the same 10 elements as MAIN, pre-existing, no page horizontal scroll. consoleErrors and requestFailures are 0 everywhere, including after clicking every link.

### F3: FIXED
Years 2025, 2026 and 2027 all show "3 categories without a budget" (Bank Fees #18, Fixed Costs, Takeaway). Archived Bank Fees and Bank Fees #17 are absent in every year. Every link (9 per viewport) returns 200 and opens the dialog "set budget · <name>"; no 404, no console error, no request failure. The disclosure count equals the number of links.

### Sanity after the YEARCHIP merge
Budget tab expanded at 1440/1024/375: no overflow, same layout as before; Taxes set from the list moves into the main table. Year cell click at 1440/1024/375: scope chips "this month only" (preselected) and "every <month>" float under the cell, no console error (yc-1440.png viewed).

### Minor (column alignment): logged follow-up, not blocking
Spent and status columns of the second table still start at different x than the main table (1440: spent 965 vs 995, status 1170 vs 1085). Readable, no overflow. Tracked as a follow-up.

### Step 3b (re-check 2)
Python-only change plus merge; templates unchanged by this fix. No float or arithmetic in the touched templates; rendered counts equal the service-provided linkable set (3 / 3 / 3); swap targets, duplicate ids (0) and failing-save behaviour unchanged.

### Final verdict
CLEAN: F1, F2, F3 fixed; column alignment is a logged non-blocking follow-up.
