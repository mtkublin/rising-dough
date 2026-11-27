# Frontend audit: OUTCLICK year cell editor closes on an outside press (2026-11-27)

Change: OUTCLICK (T-UR93, R27; branch wi/ui/sourdough/OUTCLICK, sha 8d5c6725, JS only: `app-year-cell.js`, plus the G12 allowlist for the native `pointerdown` event). Operator: "plan/year - when the chips are shown for some cell I'd expect them to disappear when I click elsewhere on the page". Fix: a capture-phase document `pointerdown` outside the editor, its chips and any cell closes the editor through the Escape/cancel path (no save).
Route: /plan?tab=year&year=2026 (the only route using app-year-cell.js).
Run: frontend-visual-audit skill (Playwright, Chromium) against the worktree code served by `tests.visual.frozen_server` on a scratch DB (`/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/OUTCLICK/o.sqlite`, never data/budget.sqlite). Seed: 2026 PLN, Groceries 500, Rent 1,200, Travel 300, 24 filler categories (page scrolls), 2 categories without a budget (collapsed list). 1440 and 1024 with the mouse; 375 with is_mobile + has_touch (DPR 2), taps via locator.tap() / touchscreen.tap(), swipe via CDP Input.synthesizeScrollGesture. All non-GET requests recorded. Screenshots in `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/OUTCLICK/shots` (viewed: open-375-heading, after-375-heading; others captured per viewport as open-/after-<w>-<target>.png, ab-, saved-, fail-<code>).

## Scenarios (Groceries March: open, type 777, press target)

Same result at 1440, 1024 and 375 (touch). "closed" = 0 editors, 0 chip groups, cell text equals the value before opening, 0 non-GET requests, heading position unchanged, cell position equal to the opened state.

| Scenario | 1440 | 1024 | 375 touch |
|---|---|---|---|
| Press page whitespace | closed | closed | closed |
| Press the h1 heading | closed | closed | closed |
| Press the collapsed "2 categories without a budget" summary | closed (list toggles, as before) | closed | closed |
| Click/tap the page tab "budget" | navigates to /plan?tab=budget, 0 POST | same | same |
| Click/tap the page nav "ledger" (top nav; bottom tab bar at 375) | navigates to /ledger, 0 POST (close does not swallow the click) | same | same |
| Open A, then press cell B (Groceries September) | only B open (1 editor, 1 chip group, month 9), A unchanged, 0 POST | same | same |
| Press a chip | editor and chips stay | same | same |
| Press inside the input | editor stays | same | same |
| Escape | cancels, 0 POST, value unchanged | same | same |
| Enter | saves (1 POST /budget/rules/5/overrides), cell shows 888.00 | same | same |
| Touch swipe that starts outside (CDP scroll gesture at the right edge) | n/a | n/a | editor CLOSES (INFO, see below) |

Note on the swipe: a touch swipe that starts on page content outside the editor fires `pointerdown` first, so it closes the editor (no save, no request) before the page scrolls; the page still scrolls. Acceptable either way per the brief; recorded as the behaviour. A swipe starting on the editor, a chip or a cell does not close it (those targets are excluded).

Observation (not caused by this change): opening a cell may scroll the year grid horizontally into view; closing does not restore that scroll. The test compared the cell position against the opened state for that reason.

## Diagnostics (Chromium, light theme)

Columns: horizontalScroll / overflowingElements / duplicateIds / consoleErrors / requestFailures.

| Route (state) | 1440 | 1024 | 375 |
|---|---|---|---|
| /plan?tab=year&year=2026 loaded | false/0/0/0/0 | false/196/0/0/0 | false/581/0/0/0 |
| after outside-press closes (whitespace, heading, summary) | false/0/0/0/0 | false/196/0/0/0 | false/471/0/0/0 |
| end of run (after Escape and Enter saves) | false/0/0/0/0 | false/196/0/0/0 | false/471/0/0/0 |

The non-zero overflowingElements at 1024 and 375 are the year grid cells inside `.rd-table-scroll.rd-year__scroll` (`overflow-x: auto`, the horizontal scroller); the document itself does not scroll (horizontalScroll false). It is the grid's designed behaviour (the CHIPMOB record shows the same, capped at 20) and independent of a JS-only change; the 375 count drops 581 to 471 only because the grid scrolled to the opened cell. Blocking signals: none (consoleErrors, requestFailures, duplicateIds all 0).

## Step 3b

- Templates: not touched (JS and one architecture allowlist line), so no arithmetic, float or literal to check in templates; displayed numbers are the server-rendered cell texts, unchanged by an outside close (cell text equals the pre-open value in every scenario).
- Failing saves visible: forced 404, 409, 500 on POST /budget/rules/*/overrides with Enter at 1440: editor stays open, cell unchanged (300.00), visible alert "That item was not found...", "That item changed in the meantime. Reload and try again.", "Something went wrong on our side. Try again." respectively.
- Swap targets: the editor is created and removed client-side; `#modal-root` unchanged. Ids: 0 duplicates after every close.
- HX events: no `HX-Trigger` added or removed.

## Findings

None. STATUS: CLEAN.
