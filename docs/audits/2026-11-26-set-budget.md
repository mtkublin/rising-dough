# Frontend audit: BUDUX set budget button (2026-11-26)

Change: BUDUX (branch wi/ui/sourdough/BUDUX, sha cb627b64): /plan?tab=budget unbudgeted rows get a "set budget" button, budgeted rows the menu item "edit budget", dialog scope labels, `#budget-hint` while no category has a budget; the Plan/year unbudgeted disclosure opens the same dialog.
Run: frontend-visual-audit skill (Playwright, Chromium) against a scratch DB (never data/budget.sqlite), Nov 2026 data: Groceries 123.45, Rent 1,200.00, Fun 40.00 spent, PLN.
Viewports: 1440, 1024, 375 (light) and 375 dark. Screenshots in `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/bx/shots` (viewed: A-budget-375d, A-dialog-bad-amount, B-edit-dialog-375).

## Routes x viewports

Columns: horizontalScroll / overflowingElements / duplicateIds / consoleErrors / requestFailures.

| Route (state) | 1440 | 1024 | 375 | 375 dark |
|---|---|---|---|---|
| /plan?tab=budget, no budgets | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| set budget dialog open (Groceries) | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| /plan?tab=budget, some budgets | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| row menu open | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| edit budget dialog open | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| /plan?tab=year, unbudgeted disclosure open | false/0/0/0/0 | false/14/0/0/0 | false/20/0/0/0 | false/20/0/0/0 |
| year: set budget dialog (Fun) | false/0/0/0/0 | false/14/0/0/0 | false/20/0/0/0 | false/20/0/0/0 |

Totals: horizontalScroll=0, duplicateIds=0, consoleErrors=0, requestFailures=0 outside forced failures (the 4 console errors after the forced 500/404/409 submits at 1440 are the browser logging those injected responses). overflowingElements=0 on all budget-tab states; on /plan?tab=year at 1024/375 the 12-month `table.rd-year` (right edge 1198 / 1182) is reported, with no page horizontal scroll (it sits in its own scroller). Identical on ui/sourdough (main checkout, same data: 20 at 1024 and 375 before the disclosure is opened), so pre-existing and not caused by BUDUX.

## Step 3b

- Button fit: at 375 the "set budget" button sits inside the spent/budget cell (button right edge 343 = cell right edge 343, height 44), rows stay two-line, no wrap breaking the row; also 1024 (706/706) and 1440 (1066/1066).
- Dialog: title "set budget · Groceries", scopes "this month only" / "every november" / "every month (default)", "every month (default)" preselected, at all widths. Year disclosure (Fun): same title and default preselected.
- Save with default scope (100.50): Groceries row shows "123.45 / 100.50", "over 22.95"; `#budget-hint` count 1 -> 0; DB budget_defaults (5, 10050). Year-disclosure save 55.00: Fun row "40.00 / 55.00", "left 15.00". Rent "this month only" 1300.00: row "1,200.00 / 1,300.00", "left 100.00". Rendered numbers equal stored minor units.
- Failing saves: "abc" -> 422, field error "enter an amount of 0 or more" visible under the amount; empty amount blocked by native required ("Please fill out this field."); forced 500/404/409 each show a visible banner (500 "Something went wrong on our side. Try again.", 404 "That item was not found...", 409 "That item changed in the meantime...") and the dialog stays open, not left looking saved.
- Template logic: no `float`, `/ 100`, `* 100` in budget-line.html or pages/plan/budget.html (rg). Swap target #modal-root matches one element; no duplicate ids after swaps.
- "edit budget" menu item: opens "edit budget · <cat> · Nov 2026" with the amount prefilled; Rent (one-off budget) opens with "this month only" checked and 1300.00.

## Findings

1. Behaviour: "edit budget" on a row whose budget is the default tier (Groceries, 100.50 every month) opens with "this month only" selected, not the row's current tier "every month (default)" (all viewports; screenshot /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/bx/shots/B-edit-dialog-375.png). The brief expects the dialog to open with the row's current tier; the menu link carries no tier parameter (budget-line.html, edit budget `hx-get` has no `tier=`), while the "set budget" button passes `tier=default`. Saving unchanged therefore creates a one-off override instead of editing the default.
2. Triage, pre-existing: /plan?tab=year reports 14/20 overflowingElements at 1024/375 (table.rd-year, no page scroll), same on ui/sourdough.
3. Observation, not verified on ui/sourdough: with no budgets the hero reads "3 over" / "0.00 committed", and the Total row "0.00 / 0.00" excludes unbudgeted spend, while rows show spend with "no budget".
