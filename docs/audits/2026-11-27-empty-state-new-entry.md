# Frontend audit: empty-state new entry opens the dialog in place (EMPTYNE)

Date: 2026-11-27. Item EMPTYNE, branch wi/ui/sourdough/EMPTYNE, audited sha 8de0c97a. Task T-UR83.
Run with the frontend-visual-audit skill (Playwright, Chromium) against two fresh scratch DBs (migrated, seeded accounts "Bank (PLN)" and "Visa (PLN)", categories Groceries and Salary, login user seeded, no transactions and no planned rows), env=dev, 127.0.0.1. data/budget.sqlite untouched.

Change: the "[ new entry ]" links in `fragments/states/planned-empty.html` and `fragments/states/ledger-first-run.html` gain `hx-get`, `hx-target="#modal-root"`, `hx-swap="innerHTML"` (href kept for no-JS), same pattern as recurring-empty (docs/audits/2026-11-27-recurring-empty-and-day.md).

## Routes and diagnostics

Columns: horizontalScroll / overflowingElements / duplicateIds / consoleErrors / requestFailures.

| Route / step | 1440 | 1024 | 375 |
|---|---|---|---|
| /ledger?view=actual, first-run empty state | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| same, new-entry dialog open | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| same, after forced 404, 409, 500 on POST /transactions | false/0/0/3/0 (a) | false/0/0/3/0 (a) | false/0/0/3/0 (a) |
| same, after real save (entry listed, flash) | false/0/0/3/0 (a) | false/0/0/3/0 (a) | false/0/0/3/0 (a) |
| /ledger?view=planned, empty state | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| same, new-entry dialog open (planned tab) | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| same, after forced 404, 409, 500 on POST /planned | false/0/0/3/0 (a) | false/0/0/3/0 (a) | false/0/0/3/0 (a) |
| same, after real save (entry listed, flash) | false/0/0/3/0 (a) | false/0/0/3/0 (a) | false/0/0/3/0 (a) |

(a) The 3 console errors are the browser's "Failed to load resource" lines for the three deliberately forced error responses (404, 409, 500). The pages were at 0 before forcing. No pageerror, no CSP violation event, no failed or 4xx static request.

Screenshots (viewed: planned after save at 375, first-run failed save at 1440; the rest captured, diagnostics read from rows.json): scratchpad dirs
`/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/EMPTYNE/shots-first` and `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/EMPTYNE/shots-planned` (01-empty, 02-dialog, 03-failed-save-500, 04-after-save per width).

## Behaviour (T-UR83)

- Both links render `hx-get=/add?when=happened&dialog=1`, `hx-target=#modal-root`, `hx-swap=innerHTML` and the same `href`. One empty-state link per page at every width.
- Click: the dialog "new entry" opens; URL unchanged (/ledger?view=actual and /ledger?view=planned), no navigation to a bare fragment. 1440, 1024, 375.
- Ledger first-run: category Groceries, amount 75.00, save: POST /transactions saved, dialog closed, the same page shows 75.00 (no "No entries yet."), flash "Transaction saved", 1 DB row.
- Planned empty: planned tab, due 2026-12-20, Groceries, 75.00, save: POST /planned saved, dialog closed, the same page lists the planned row (-75.00 PLN, 20 DEC, promote action), planned tab count 1, flash "Planned entry saved", 1 DB row.

## Step 3b

1. Swap targets: `#modal-root` count is 1 before the click, with the dialog open and after save.
2. Failing saves visible: POST /transactions and POST /planned forced to 404, 409 and 500 from the open, fully filled dialog: dialog stays open with a visible error each time ("That item was not found. It may have been removed.", "That item changed in the meantime. Reload and try again.", "Something went wrong on our side. Try again."). Not left looking saved.
3. No arithmetic in templates: rg for float, / 100, * 100 and set in both touched fragments: no match; the diff only adds hx attributes.
4. Money formatting by currency: not touched (no amount rendered by the diff); JPY not checked, out of scope.
5. Rendered numbers: saved 75.00 shows as -75.00 PLN in the hero and row; DB amount 75.00 PLN (7500 minor, one row).
6. Duplicate ids: 0 at every step including after the swap and after save. No new HX-Trigger emitters or listeners in the diff.
7. Scratch data only.

## Findings

None.
