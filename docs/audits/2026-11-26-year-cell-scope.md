# Frontend audit: YEARUX year cell scope chips (2026-11-26)

Change: YEARUX (T-UR56, F4.8a; branch wi/ui/sourdough/YEARUX, sha d208ed63): the /plan?tab=year inline cell editor gets a scope chip row (this month only / every <month> / every month (default)), preselected to the cell's tier; Enter saves with the scope, Escape cancels, a modified click or no script opens the override dialog.
Run: frontend-visual-audit skill (Playwright, Chromium) against a scratch DB (never data/budget.sqlite): 2026 PLN, Groceries default 500.00 + one-off Mar 321.00 + recurring Jun 700.00, Rent default 1,200.00, Travel one-off Aug 900.00, Fun unbudgeted (one expense).
Screenshots in `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/YEARUX/shots` (viewed: editor-1440, editor-1024, editor-375, forced-500).

## Routes x viewports

Columns: horizontalScroll / overflowingElements / duplicateIds / consoleErrors / requestFailures.

| Route (state) | 1440 | 1024 | 375 |
|---|---|---|---|
| /plan?tab=year&year=2026 | false/0/0/0/0 | false/20/0/0/0 | false/20/0/0/0 |
| year, scope editor open (Groceries Apr) | false/0/0/0/0 | false/20/0/0/0 | false/20/0/0/0 |
| year after a default-scope save | false/0/0/4/0 | - | - |
| override dialog from a year cell (shift-click) | false/0/0/4/0 | false/20/0/0/0 | false/20/0/0/0 |

Totals outside forced failures: duplicateIds=0, requestFailures=0, consoleErrors=0. The 4 console errors at 1440 are the browser logging the injected 500/404/409 responses and the 422 from the empty amount (no script error). overflowingElements=20 at 1024/375 is the 12-month `table.rd-year` in its own scroller (no page horizontal scroll), identical with the editor closed and open: pre-existing, T-UR71, not blocking.

## Step 3b

- Preselect: Groceries Mar (one-off) -> "this month only"; Groceries Jun (recurring) -> "every june"; Groceries Apr (default) -> "every month (default)"; Travel Aug (one-off) -> one-off; Travel Feb (unset month of a budgeted category) and Rent May -> default. Chip labels: "this month only", "every april", "every month (default)". The unbudgeted Fun link opens "set budget · Fun" with default checked (no inline editor for unbudgeted rows; they use the dialog).
- Default scope: Groceries Apr 612.34 + Enter -> Jan, Feb, Apr, May, Jul..Dec show 612.34; Mar (321.00 one-off) and Jun (700.00 recurring) unchanged; DB budget_defaults (5, 61234). Focus returns to the Apr cell.
- "every september": Sep 444.44 in 2026, and 2027 Sep also 444.44 (2027 Jun 700.00, Mar/Apr 612.34); DB budget_recurring_overrides (5, 9, 44444). Focus returns to the Sep cell.
- "this month only": Oct 55.50 in 2026 only; 2027 Oct 612.34; DB one-off (5, 2026, 10, 5550).
- Escape: cell unchanged (500.00 then), DB unchanged, editor closed, focus on the cell (also when pressed from a chip).
- Invalid amounts: typed "abc" is rejected client side (field stays empty; fill("abc") keeps the old value), Enter then answers 422 and the dialog shows "enter an amount of 0 or more"; direct POST "abc" returns 422 with the same error retargeted to #modal-root; empty amount: same 422 dialog. DB unchanged each time. Forced 500/404/409: visible banner ("Something went wrong on our side. Try again." / "That item was not found..." / "That item changed in the meantime..."), cell and DB unchanged.
- Keyboard: Tab from the amount lands on the checked chip (one tab stop for the radio group), ArrowRight switches the scope, Escape from a chip cancels; Enter on a focused cell link opens the editor with focus in the amount.
- No-JS / modified click: the cell href (/budget/rules/6/overrides/new?year=2026&month=2&tier=one-off) opens the override dialog; shift-click opens "edit budget · Rent · Feb 2026".
- Template logic: no `float`, `/ 100`, `* 100` or set blocks in year.html or year-cell-editor.html (the chip texts come from the view model); the editor is a cloned template, the swap target #modal-root / #main match one element, no duplicate ids after saves (diagnostic re-run).

## Findings

1. Layout: the chip row is a 437 px wide overlay under the edited cell (1440: x 544..981; 1024: 467..905; 375: 149..587) and covers neighbouring cells of the next row (Rent Apr..Aug at 1440 and 1024; 10 to 12 cells overlap the rect by diagnostic) while the editor is open; the values behind it cannot be read. The chips themselves are readable and do not overlap each other. At 375 the row is wider than the grid scroller, so the third chip is only reachable by scrolling the grid (the first chip is cut at the viewport edge, see /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/YEARUX/shots/editor-375.png). Brief: chips not overlapping neighbouring cells. Suggested: anchor the row so it ends inside the grid and, at narrow widths, wrap the chips or stack them.
2. Observation: the no-JS / shift-click dialog on a default-tier cell (Rent Feb) opens with "this month only" checked (cell href carries tier=one-off), while the inline editor preselects "every month (default)" for the same cell; the two entry points disagree.
3. Triage, pre-existing: table.rd-year overflow at 1024/375 (T-UR71).
