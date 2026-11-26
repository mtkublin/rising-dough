# Frontend visual audit: F9 dialog residuals (2026-11-26)

Item F9, branch `wi/ui/sourdough/F9`, audited sha 057b057. Skill `frontend-visual-audit` (Playwright, Chromium), scratch DB built by `tests/visual/handoff_seed.py` (modifier `recurring-board`), served by `tests.visual.frozen_server` at 2026-10-31. Never `data/budget.sqlite`.

## Routes x viewports

Routes: `/add?when=happened`, `/add?when=repeats`, the Taxes edit dialog `/recurring/6/edit` (opened from `/ledger?view=recurring`). Viewports 1440, 1024, 375 (9 rows).

| Route | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /add?when=happened | 1440 | false | 0 | 0 | 0 | 0 |
| /add?when=happened | 1024 | false | 0 | 0 | 0 | 0 |
| /add?when=happened | 375 | false | 1 (pre-existing) | 0 | 0 | 0 |
| /add?when=repeats | 1440 | false | 0 | 0 | 0 (5 forced 422 resource logs) | 0 |
| /add?when=repeats | 1024 | false | 0 | 0 | 0 (5 forced 422) | 0 |
| /add?when=repeats | 375 | false | 2 (pre-existing) | 0 | 0 (5 forced 422) | 0 |
| /recurring/6/edit (Taxes) | 1440 | false | 0 | 0 | 0 (4 forced 422) | 0 |
| /recurring/6/edit (Taxes) | 1024 | false | 20 (pre-existing) | 0 | 0 (4 forced 422) | 0 |
| /recurring/6/edit (Taxes) | 375 | false | 2 (pre-existing) | 0 | 0 (4 forced 422) | 0 |

"Forced 422": Chromium logs "Failed to load resource ... 422" for the intentional 422 preview/save responses; no script errors, no 4xx/5xx on GETs.

Pre-existing overflowingElements, identical on MAIN (ui/sourdough e92f3d3, same DB copy): 375 `label.rd-chip-option` right=405 (381 in the edit dialog), the nowrap, `overflow-x: auto` recents row (deliberate scroller, F9 changes no CSS); 1024 the ledger recurring board table behind the dialog (`td.rd-row__actions` right=1058, clipped, no horizontal scroll).

## Behaviour checks (F9)

- Chip pick: clicking the 3rd recent chip (Transport) moves it first and checks it: `Transport*, Groceries, Takeaway, Nights Out`; nothing dropped.
- Search pick of a recent (Nights Out): moves to front, checked, no hidden category input.
- Search pick outside recents (Travel): chips unchecked, hidden `category=22` set, opener shows Travel; a later chip click leads again.
- Formula, empty component: preview 422 `invalid_source`, span present but `hidden`, no visible text, no aria-live region. Percent only (no category): same, hidden. SAVE attempt: dialog stays open, visible "Pick a category" (new entry) / "coefficient is required for formula rules" (Taxes edit).
- Cycle (Taxes source = Taxes) visible: "a formula cannot reference its own category". Non-positive visible: "formula resolved to a non-positive amount". Valid Taxes rule shows "next amount 3,002.00 PLN".

## Findings

1. Behavior / A11y (keyboard), blocking for the keyboard requirement: with a recent chip checked and focused, ArrowRight selects the next radio in DOM order, `leadRow` moves that label to the front (`combobox.js` `leadRow`, `before()`), and the focused radio loses focus (`document.activeElement` is BODY). Further arrows do nothing. Observed at all viewports: from `Transport*, Groceries, ...` ArrowRight gives `Groceries*, Transport, ...`, focus BODY; a second ArrowRight and ArrowLeft leave the selection unchanged. The order also flips on each pick, so arrow stepping cannot walk the group. Suggested fix: re-focus the checked radio after reordering (or reorder without detaching the focused element, or skip the move on keyboard-driven change).

No other findings.

## Step 3b

- Swap targets: `#modal-root` and `.rd-formula__result` are single elements before and after swaps; duplicate ids re-checked after interactions: 0.
- Failing saves: forced 404, 409, 500 on POST `/transactions`, `/recurring`, `/recurring/6`: dialog stays open and shows a visible error each time ("not found", "changed in the meantime", "Something went wrong"); not left looking saved.
- Template logic: `formula-result.html` (only template touched) and `combobox.js` contain no float, `/ 100`, `* 100` or `set`; the hidden decision uses `result.code`.
- Rendered number: Taxes preview "3,002.00 PLN" is the service preview response (not re-derived in the template); ledger board value 3,080.65 is for the stored rule, untouched by F9.
- Listeners: no new HX-Trigger events.

## Screenshots

Under the scratchpad `shots/` directory (not committed), viewed: `375__repeats__formula-save-422.png` (visible "Pick a category" error, formula row intact), `1440__taxes__cycle.png` (cycle state; full-page capture shows the dialog over the board, semi-transparent mid-transition, no layout break). Others captured per route and viewport: `<vp>__<route>__initial|final|keyboard|formula-*|taxes__*|fail__*.png`.
