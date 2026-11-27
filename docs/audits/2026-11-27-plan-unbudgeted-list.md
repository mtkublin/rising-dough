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
