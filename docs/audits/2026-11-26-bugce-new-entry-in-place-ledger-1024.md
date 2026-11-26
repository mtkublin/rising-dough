# Frontend audit: BUGCE (new entry opens in place; T-UR49 planned/recurring actions at 1024)

Branch wi/ui/sourdough/BUGCE at 6efbd435 (base 7ad71800). Scratch DB: handoff seed (tests/visual/handoff_seed.py,
frozen 2026-10-31), never data/budget.sqlite. Run with the frontend-visual-audit method (Playwright, chromium).
Screenshots (viewed): /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/bugce/out/*.png (light_*, dark_*, open_*, dialog_*, 3b_server_error.png, planned_after_save.png).

## Routes x viewports (diagnostics)

Routes: /ledger, /ledger?view=planned, /ledger?view=recurring, /today, /plan.
Viewports: 1440, 1024, 375 light; 1440 and 375 dark. Every one of the 40 page rows:
horizontalScroll=0, overflowingElements outside a scroll container=0, duplicateIds=0, consoleErrors=0, requestFailures=0.
(375 /today, /ledger: 1 element reports right > viewport, always inside a horizontal scroll container, the recents chip row; 2 with the dialog open.)

| Route | 1440 | 1024 | 375 |
|---|---|---|---|
| /ledger | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /ledger?view=planned | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /ledger?view=recurring | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |
| /today | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 (1 contained) |
| /plan | 0/0/0/0/0 | 0/0/0/0/0 | 0/0/0/0/0 |

(order: horizontalScroll/overflowingElements/duplicateIds/consoleErrors/requestFailures.)

## T-UR49 planned/recurring at 1024

Table width 928 = scroll container width (scrollWidth 928, no sideways scroll); the right-most button edge equals the
container edge: every actions cell (promote / kebab) fully visible. Screenshot light_1024__ledger_viewplanned.png checked.
1440: layout matches the handoff planned/recurring pages (columns, overrides panels, kebabs); no regression
(light_1440__ledger_viewrecurring.png). 375: unchanged mobile cards, table 311 wide, no clipping.

## New entry in place

Openers checked on all five routes: top-bar [ new entry ] (1440, 1024), tab-bar "+" (375), the n key and palette "New entry" (all widths): 45/45 open
the dialog in #modal-root, URL unchanged, Escape closes it, no console error, no request failure, no duplicate ids.
Dialog at 375 on /today (dialog_375_today.png): recents chips populated (GROCERIES, TAKEAWAY, TRANSPORT, NIGHTS OUT),
no horizontal scroll; chip row scrolls inside its container.
Save from /ledger?view=planned (planned tab, category, account Checking, 12.34): dialog closes, URL stays, row "BUGCE probe" appears
in the list, flash "Planned entry saved" visible.

## Step 3b

- Swap targets: all hx-target selectors on /ledger?view=planned match exactly one element; one #modal-root.
- Failing save: empty amount. Native required validation blocks first (validationMessage "Please fill out this field."); with
  validation bypassed the server 422 shows "amount must be a decimal number within range" under the amount, dialog stays open
  (3b_server_error.png). No category: "Pick a category" shown, dialog open. The 422 appears as a Chrome "Failed to load resource" console line only
  for these forced failures; not counted (no 422 in the normal sweep). 404/409/500 not forced (no new endpoints; the dialog route is unchanged).
- Template logic: the diff in templates only adds hx-get/hx-target/hx-swap and data-hx-get attributes; no arithmetic, float or literal values.
- No new HX-Trigger emitters or listeners. Rendered numbers unchanged (no value-bearing template touched).

## Findings

None blocking. Observation: none; the planned-save flash is present.
