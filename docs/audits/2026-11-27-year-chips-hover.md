# Frontend audit: YEARCHIP year cell hover chips (2026-11-27)

Change: YEARCHIP (T-UR77, R16+R17; requirement F4.8a amended 2026-11-27; branch wi/ui/sourdough/YEARCHIP, sha c35f405d). The /plan?tab=year inline cell editor now offers exactly two chips, "this month only" (always preselected) and "every <Month>", as a position:fixed group placed under the clicked cell by app-year-cell.js (no outer box, nothing shifts), clamped to the viewport, re-placed on scroll/resize; colours from --color-ink/--color-panel/--color-rule/--color-raised; the year cell never writes the default tier (server answers 422 for tier=default with origin=year); the dialog / no-JS link opens on "this month only".
This record supersedes the 3-chip parts (chip row as an in-flow table row, "every month (default)" chip, default-tier preselect and `tier=default` hrefs) of docs/audits/2026-11-26-year-cell-scope.md; the rest of that record (save semantics, 422 and forced-failure handling) is re-verified below.
Run: frontend-visual-audit skill (Playwright, Chromium), scratch DB (never data/budget.sqlite): 2026 PLN, Groceries default 500.00 + one-off Mar 321.00 + recurring Jun 700.00, Rent default 1,200.00, Travel one-off Aug 900.00. Light and dark theme (color_scheme plus localStorage rd-theme).
Screenshots in `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/YEARCHIP/shots` (viewed: light-1440-Groceries-6, dark-1440-Travel-7, light-375-Travel-12, dark-375-Travel-12; the rest are captured per cell as <theme>-<viewport>-<category>-<month>.png, plus follow-*, hfollow-*, bottom-edge, invalid, dialog-year, dialog-budget, forced-*).

## Routes x viewports

Columns: horizontalScroll / overflowingElements / duplicateIds / consoleErrors / requestFailures. Measured on the loaded page and again after the six open/close cycles.

| Route (state) | 1440 light | 1440 dark | 1024 light | 1024 dark | 375 light | 375 dark |
|---|---|---|---|---|---|---|
| /plan?tab=year&year=2026 | false/0/0/0/0 | false/0/0/0/0 | false/20/0/0/0 | false/20/0/0/0 | false/20/0/0/0 | false/20/0/0/0 |
| year after 7 editor open/close cycles | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 | false/20/0/0/0 | false/20/0/0/0 |
| /plan?tab=budget (dialog) , override dialog from year (shift-click) | false/0/0/0/0 | - | - | - | - | - |
| year after a real save (3 forced-failure console lines) | false/0/0/3/0 | - | - | - | - | - |

Totals outside forced failures: duplicateIds=0, requestFailures=0, consoleErrors=0, horizontalScroll=false. The 3 console errors on the last row are the browser logging the injected 404/409/500 (and the 422 of the empty amount in the earlier pass), not script errors. overflowingElements=20 at 1024/375 is the 12-month table.rd-year inside its own scroller (no page horizontal scroll): pre-existing, T-UR71, not blocking (the 1024 "after cycles" re-measure reads 0 because the scroller had been left scrolled).

## Chip placement (per theme x viewport)

For Groceries and Travel (top and bottom row) in Jan, Jun/Jul and Dec (first, middle, last column), after a vertical page scroll (Travel Mar, scrollY 200) and, at 375, with the grid scrolled fully right for months 7 and 12:
- exactly 2 chips (THIS MONTH ONLY / EVERY <MONTH>), position fixed, no outer border (0px), transparent background, no shadow on the group; "this month only" checked in all 36 opens.
- group top = editor bottom + 4 px in every case (a small constant gap, directly under the cell); group inside [0, innerWidth] in every case, e.g. 375: Dec group x 96..367, Jan x 103..367; 1440: Dec x 1161..1432. Rows below do not move (row tops identical open vs closed, rowShift=0 in all 36 opens); editor height 40 px equals the cell height (40 px).
- the chips overlay the row below the cell (rect y +4..+44) by design (hovering); they cover that row's values only while the editor is open.
- Escape removes the group and the editor (0 and 0 left) in every case.
- Follow: at 1440x420 scrolling the page by 0/60/120 px keeps the 4 px gap (group top 464/404/344 against editor bottom 460/400/340); resizing 1440 to 1000 wide re-places it (x 549); at 375 scrolling the grid by 0/80/200/max keeps the 4 px gap and the group inside the viewport (x 110..367, then 8..265 as the cell scrolls off to the left, group clamped at the viewport edge); no detached floating chips left after close.

## Colours

Both themes read from the tokens: light chips: ink rgb(18,16,16) on --color-raised #f3eee7 (checked, ink border) / --color-panel #faf7f3 with --color-rule #ece6de border (unchecked); dark chips: ink rgb(237,237,230) on #1d1d19 (checked) / #161613 with #2a2a26 border (unchecked). The reference control (topbar help button) shows the same ink colour in each theme (light rgb(18,16,16), dark rgb(237,237,230)). The earlier dark-in-light fault is gone (viewed light-1440-Groceries-6 and light-375-Travel-12: light chips on a light panel; dark-1440-Travel-7 and dark-375-Travel-12: dark chips).

## Step 3b

- Preselect: always "this month only" (36 of 36 opens, incl. default-tier Rent cells, recurring Jun and one-off Mar cells). Cell hrefs (no-JS / modified click) all carry tier=one-off, including the default-tier Rent Feb, recurring Groceries Jun and unset Travel Feb; shift-click on Rent Feb opens the override dialog with "this month only" checked (radios: this month only, every february, every month (default)).
- Keyboard: Tab from the amount lands on the checked chip ("this month only"; one tab stop), ArrowRight switches to "every <month>", Enter saves with that scope; mouse click on a chip then Enter works; Escape (also after Tab to a chip) leaves the cell and DB unchanged, editor closed, focus on the cell.
- DB exact: Groceries Sep 444.44 "every september" -> budget_recurring_overrides (5, 9, 44444), 2026 and 2027 Sep both show 444.44, 2027 Oct unchanged 500.00; Groceries Oct 55.50 "this month only" -> one-off (5, 2026, 10, 5550), 2027 Oct stays 500.00; Rent Apr 1111.11 + Enter without touching chips -> one-off (6, 2026, 4, 111111), Rent May unchanged 1,200.00 and no budget_defaults row changed; Travel Feb 77.00 via mouse chip "every february" -> recurring (8, 2, 7700).
- Server rejects the default from the year cell: POST /budget/rules/<id>/overrides with tier=default and origin=year answers 422, no DB change; the same POST without origin (the dialog) answers 200 and writes budget_defaults (5, 12300).
- Budget tab: the Row menu "edit budget" dialog (href tier=default) still shows all three radios with "every month (default)" checked; saving 610.10 writes budget_defaults 61010 and closes the dialog.
- Failing saves visible: empty amount from the year cell answers 422 and #modal-root shows "enter an amount of 0 or more" with the scope radios (DB unchanged); forced 404 / 409 / 500 each show a visible banner ("That item was not found...", "That item changed in the meantime...", "Something went wrong on our side. Try again."), cell and DB unchanged, editor still open.
- Template logic: no float, / 100, * 100 or set blocks in pages/plan/year.html and fragments/rows/year-cell-editor.html (rg, 0 hits); chip labels come from the view model (data-recurring-label). Swap targets #main and #modal-root match exactly one element before and after a save; no duplicate ids after a save (diagnostic re-run).
- Test-side note, not a finding: typing in the same millisecond as the opening click appended to the prefilled value (selection of the prefilled text is not instantaneous); with a 250 ms pause the typed value replaces it as for a user.

## Findings

1. Layout (minor): no vertical clamp. When the edited cell sits at the very bottom of the viewport the chips fall outside it: 1440x452, Travel May, editor bottom 452, group y 456..496 (viewport height 452), inVp=false (/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/YEARCHIP/shots/bottom-edge.png). They follow the cell and are reachable by scrolling, and focusing the input does not scroll them in. Brief: "kept inside the viewport". Suggested: in app-year-cell.js place(), when box.bottom + group height > clientHeight, put the group above the cell (top = box.top - height) or scroll the cell into view with room for the group.
2. Triage, pre-existing: table.rd-year overflow at 1024/375 (T-UR71).

Status: FINDINGS (one minor layout finding; everything else in the brief verified).

## Re-check 2026-11-27 (d79d65bf, sha 3d5d43df)

Scope: the flip-above fix for finding 1 (place() in app-year-cell.js). Same scratch DB seed, light and dark, 1440x452, 1024x452 and 375x452 (plus 900 high after a resize). Screenshots in `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/YEARCHIP/shots2` (viewed: light-1440-bottom-Travel-5; the rest captured as <theme>-<width>-bottom-<category>-<month>.png and <theme>-<width>-mid.png).

Result per check (36 bottom/mid checks, light and dark identical):
- Cells mid-viewport (Groceries Jun, 1440/1024/375): chips below the cell, inside the viewport, 4 px gap, no overlap. OK.
- Cells at the viewport bottom (Travel Jan, May, Dec, Rent Jul at 1440 and 1024): chips are now above the cell and fully inside the viewport (e.g. 1440x452 Travel May: group y 376..416, editor y 412..452, vh 452). Finding 1 (chips below the viewport) is fixed.
- Re-place on scroll and resize: scrolling the page so room appears below flips the chips back below (group y 360..400, editor 316..356) and scrolling back flips them above; resizing 452 -> 900 puts them below (y 464..504) and back to 452 puts them above. OK.
- Horizontal clamp unchanged: 1440 Dec x 1161..1432, 1024 Dec x 745..1016, 375 Jan x 103..367, Dec x 96..367, all inside [0, innerWidth].
- 375: the page is short enough that the bottom cells never reach the viewport bottom in my setup (editor y 292..332 of 452), so the chips stay below and fit; the flip itself is the same code path as at 1440/1024.
- Escape removes the group and the editor (0 and 0) in every case.

Diagnostics (horizontalScroll / overflowingElements / duplicateIds / consoleErrors / requestFailures), load and after the open/close cycles: 1440 light and dark false/0/0/0/0 both times; 1024 false/20/0/0/0 on load (table.rd-year in its own scroller, T-UR71, pre-existing) and false/0/0/0/0 after; 375 false/20/0/0/0 both times (same pre-existing scroller). No duplicate ids, no console errors, no failed requests.

Step 3b: only app-year-cell.js changed (no template, no save path); the save, 422 and forced-failure results above stand. No arithmetic or float in templates touched.

New finding 3 (Layout, minor): the flipped chips overlap the edited cell by 4 px. .rd-year-editor__scope has margin-top: var(--space-1) (overrides.css:33-41), which is the 4 px gap below the cell, but place() uses GAP = 0 and ignores that margin: above = box.top - height puts the group top at box.top - height + 4, so the group bottom sits 4 px inside the editor (1440x452 Travel May: group y 376..416, editor y 412..452, overlapEditor=true in every flipped case). The chips cover the top frame of the cell input (viewed light-1440-bottom-Travel-5: the input's top edge is hidden behind the chips); the input interior and text stay visible. The same ignored margin also makes fitsBelow optimistic by 4 px (chips could end up to 4 px below the viewport). Suggested: in place() count the margin (height = offsetHeight + parseFloat(getComputedStyle(group).marginTop); above = box.top - height so the group, margin included, ends at box.top; fitsBelow with that height), or flip to margin-bottom when above.

Final verdict: FINDINGS (finding 1 fixed; finding 3 minor, new; finding 2 pre-existing).
