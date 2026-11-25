# Frontend visual audit: T-UR10a ledger planned, recurring and recently deleted

Task: T-UR10a, branch wi/ui/sourdough/UR10a at 512a9bef. ADR-0027, ADR-0107, ADR-0134, ADR-0150.
Method: frontend-visual-audit skill (Playwright, chromium), heavy lock /tmp/ui-redesign-heavy.lock taken and released.
Data: copy of data/demo.sqlite (migrated, login user seeded) plus four planned rows (overdue, due today, tomorrow, +10,000.00 income), a fresh empty
copy (no planned, no recurring), and a third copy with a JPY and an EUR account, cached FX rates, two planned rows and two rules. Servers on
127.0.0.1:8131, 8132, 8133. data/budget.sqlite not touched. Screenshots: /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR10a/shots/

## Routes and viewports

/ledger?view=planned (data, empty), /ledger?view=recurring (data, empty), /ledger/recently-deleted. Each at 1440, 1024 and 375, light and dark (30 rows).
Plus row menu open (planned, recurring), edit planned dialog, override dialog, expanded recurring detail, remove-override dialog at the same 6 combinations (36 rows).

| State | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|
| all 15 route states, 1440, both themes | 0 | 0 | 0 | 0 | 0 |
| planned and recurring with data, 1024 | 0 | 20 (table region, see F5) | 0 | 0 | 0 |
| planned and recurring with data, 375 | 0 | 1 (`a.rd-tabs__tab`, see F5) | 0 | 0 | 0 |
| empty states, recently deleted, all widths | 0 | 0 | 0 | 0 | 0 |
| menus and dialogs, 1440 | 0 | 0 | 0 | 0 | 0 |

Every id-based hx-target matches exactly one element. No duplicate ids after edit, promote, delete, undo, override, remove, skip, deactivate and restore.
Console lines only appear for the deliberate 422 (amount 0) and the forced 404, 409 and 500 responses.

## Comparison with the handoff (pages/ledger/planned, recurring, their --empty, recently-deleted, overlays row-menu--planned, row-menu--recurring, override--remove)

Boards rendered at 1440, 1024 and 375 (light). Hero band and figure, tab pills with counts, filter bar, table columns, status text (overdue, due today, in N days),
chips, row menu (popover at desktop, bottom sheet at 375, cancel last, delete in the danger colour), expand arrow, overrides badge and list, remove confirm,
recently-deleted sections all match in structure and type. Menu items: planned promote (phone only), edit, delete; recurring promote, override, skip next, edit,
delete, as specified in the task. Deviations that the board shares: see F4 and F5.

## Behaviour (all run at 1440 light against the demo copy)

| Action | Result |
|---|---|
| planned edit (menu) | UR10b dialog opens; amount 0 gives 422 with the error summary in the dialog; 160.50 saves, dialog closes, table refetched once, row −160.50, flash "Planned entry saved" |
| planned promote | dialog, submit, table refetched, row shows "✓ promoted"; no flash or toast (F2) |
| planned delete | native confirm, row removed after refetch, toast "Planned entry deleted" with undo; undo restores the row |
| recurring override | dialog; amount 0 gives visible 422; 100.00 saves, flash "Override saved · November", row −100.00 with "↺ 1 override" badge |
| remove override | expand, remove, confirm dialog, flash "Override removed", badge gone, amount back to −277.94 |
| recurring promote | dialog, submit, next due moves 01 NOV to 01 DEC, actual count 616 to 617; no flash (F2) |
| skip next | native confirm, next due 01 DEC to 01 JAN; no flash (F2) |
| delete rule (deactivate) | native confirm, tbody removed (27 to 26); no flash, no undo (F2) |
| restore deleted planned row | row leaves the list (planned view shows it again); no toast (F3) |
| restore deleted category | toast "Category restored", settings and budget stale events; row stays listed (F3) |

## Step 3b

1. Swap targets: `#ledger-table`, `#modal-root`, `#planned-table` exactly one before and after every swap. ok.
2. Failing saves: forced 404, 409 and 500 on planned delete, planned edit save, override save, skip next and rule delete each show a visible error
   ("That item was not found...", "changed in the meantime...", "Something went wrong..."); dialogs stay open, rows unchanged. ok.
3. Template arithmetic: rg over the touched templates (ledger fragments, planned and recurring rows, deleted rows, row menu, dialogs, empty states, ledger pages)
   finds no `float`, `/ 100`, `* 100`, `set` blocks, arithmetic or currency or period literals. ok.
4. Money by currency: JPY row "−12,345 JPY" and rule "−98,000 JPY" (no decimals), EUR "−25.50 EUR", "−9.99 EUR". ok.
5. Rendered equals service: planned_totals on the demo copy gives 5 items, 1 overdue, 1 due today, 7,479.71 PLN; page shows the same. recurring_monthly_totals gives
   out 13,754.94, in 23,252.61, 27 rules, next due 2026-11-01; page "−13,754.94 PLN out / in +23,252.61 · 27 rules · next due 01 nov". The FX copy (7,050.76 and
   16,345.24, 29 rules) also equals the service. Equal on first render; after an action the hero is stale (F1).
6. Listeners: `ledger-stale` has one listener on the page (table refetch via hx-trigger and app-ledger.js dialog close), emitted by every action. The restore of a category
   emits no ledger-stale (not needed). ok. Negative amounts use U+2212 everywhere (hyphen-minus before a digit: 0; menu titles, dialog hero, override deltas included). ok.

## Findings

- F1 Behavior, medium: after any planned or recurring action the hero and the tab counts are not refreshed. Only `#ledger-table` refetches on ledger-stale. After
  deleting the Fixed Costs rule the page kept "−13,754.94 PLN out · 27 rules" and tab "recurring 27"; a reload gives −13,477.00 and 26 rules. After the planned edit,
  promote and delete the hero stayed 7,479.71 (reload: 7,549.71, "4 items · 1 overdue · 0 due today"). Fix: swap the hero and tabs out of band with the table fragment
  (as the export menu already does with `oob_export`), or re-trigger them on ledger-stale. Shots: shots/flow-planned-after-delete.png, shots/flow-rec-after-delete.png.
- F2 Behavior, medium: recurring promote, skip next, delete rule and planned promote give no visible confirmation (no flash, no toast); a rule delete also has no undo.
  The row just moves or disappears. The saves that do confirm: planned edit, override save and remove (flash), planned delete (toast with undo).
  Shots: shots/flow-rec-after-skip.png, shots/flow-rec-after-delete.png, shots/flow-planned-after-promote.png.
- F3 Behavior, medium: recently-deleted restore. A category restore answers 204, so htmx does not swap and the row stays in the list (count still 3) while the toast
  says "Category restored". A planned restore removes the row but leaves the table header, the count "· 1" and no empty state, and shows no toast. Fix: answer the
  category restore with a body or HX-Reswap delete, update the section count and empty state, add the toast to the planned restore.
  Shots: shots/flow-deleted-after-cat-restore.png, shots/flow-deleted-after-planned-restore.png.
- F4 Layout, low (handoff parity): at 375 the override list in the expanded rule detail overlaps month label and amount ("Nov 2026" over "16,213.97 PLN"). The handoff board
  shows the same overlap. Shots: shots/light-375-recurring-expanded.png, shots/dark-375-override-remove-dialog.png.
- F5 Layout, low (handoff parity): at 1024 the Planned and Recurring tables scroll sideways inside `.rd-table-scroll`, so the promote button is cut and the row menu is
  off-screen until scrolled (overflowing th, td and button at right 1058; no page scroll). At 375 the ledger tab strip's third tab ends at 380 (inside its own scroll area).
  The handoff boards show the same cut at 1024 and 375. The topbar also wraps to two rows at 1024 with the owner email (shell, not this item).
  Shots: shots/light-1024-planned.png, shots/board-ledger_planned-1024-light.png.

Status: FINDINGS (F1, F2, F3 are for the implementer; F4 and F5 are handoff parity and can be triaged).
