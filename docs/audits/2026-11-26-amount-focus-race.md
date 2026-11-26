# Frontend audit: amount focus race (item RACE)

Change: `static/rd/js/amount-input.js`, the rAF-delayed `select()` on focusin now runs only if the amount still has focus. Branch `wi/ui/sourdough/RACE` at 105b038c. Audited with the `frontend-visual-audit` skill (Playwright, Chromium), scratch DB (copy of `data/demo.sqlite`, migrated, login seeded), never `data/budget.sqlite`. Scratch output: `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/shots/`, `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/result.json`.

## Routes x viewports

Routes: `/ledger`, `/ledger` + new-entry dialog (through the topbar button, or the tabbar "+" at 375), `/today`, `/today` + new-entry dialog.

| Route / state | Width | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /ledger, dialog, after tab swaps, after 422, after save | 1440 | false | 0 | 0 | 0 (note 1) | 0 |
| /today, /today dialog | 1440 | false | 0 | 0 | 0 | 0 |
| /ledger, dialog, after tab swaps, after 422, after save | 1024 | false | 0 | 0 | 0 (note 1) | 0 |
| /today, /today dialog | 1024 | false | 0 | 0 | 0 | 0 |
| /ledger | 375 | false | 1 (`a.rd-tabs__tab` right 380) | 0 | 0 | 0 |
| /ledger dialog (open, after swaps, after 422) | 375 | false | 2 (`rd-tabs__tab` 380, `label.rd-chip-option` 377) | 0 | 0 (note 1) | 0 |
| /today | 375 | false | 1 (`pre.rd-hero__loaf` right 399) | 0 | 0 | 0 |
| /today dialog | 375 | false | 2 (`rd-hero__loaf` 399, `rd-chip-option` 377) | 0 | 0 | 0 |

Note 1: the console shows only "Failed to load resource" for the deliberate 422 (empty amount) and the forced 404/409/500 of Step 3b. No JS errors, no `pageerror`.

Overflow at 375 is pre-existing: the same elements overflow by the same amounts on MAIN (`ui/sourdough`) for /ledger, /today and the ledger dialog (`rd-tabs__tab:380`, `rd-hero__loaf:399`, `rd-chip-option:377`). The JS-only change cannot cause it. `horizontalScroll` is false everywhere. Not part of RACE; send to the owner of the 375 layout.

## Behaviour checks (all three widths, identical results)

- (a) click into amount (value 12.50): selection 0..5. Shift+Tab into amount from the note: selection 0..5. Feature kept.
- (b) amount "42", move to the note, type "lunch": amount stays "42", note "lunch", focus on the note. 8 runs per width (3 click then Tab, 2 programmatic focus then Tab, 3 programmatic amount.focus() and note.focus() in the same task, the tightest race). 0 failures.
- (c) tabs in this dialog are happened / planned / repeats (there is no expense/income tab). happened -> planned -> happened with amount 77.25 and note "carry me": both carried each time, `aria-current` follows the tab.
- (d) save (amount 42.00, Groceries, note): dialog closes, flash "Transaction saved" visible, row with the note on the ledger (-42.00 PLN), DB row amount 4200 equals the rendered 42.00.
- (e) failing save (empty amount, validation bypassed): dialog stays, "Enter an amount above 0.00" and "Pick a category" shown, amount `aria-invalid=true`, typed note "keep this note" kept.
- /today new-entry dialog: amount 9, Tab to the note, "todaynote": both kept.

## Step 3b

- Swap targets: `#modal-root` and `.rd-dialog__hero` single-match (the tab swaps and the 422 re-render ran without console errors; duplicate-id diagnostic 0 after every swap).
- Failing saves visible: forced 404, 409 and 500 on POST /transactions each show a visible alert ("That item was not found...", "That item changed in the meantime...", "Something went wrong on our side. Try again.") and the dialog stays open, not looking saved.
- No templates touched by this change (JS only), so no arithmetic/float check applies; rendered amount equals the stored value (above).
- No duplicate ids after any swap.

## Screenshots viewed

`/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/shots/`: `1440_ledger_saved.png` (flash and new row), `375_ledger_dialog_error.png` (field errors, note kept), plus `{1440,1024,375}_ledger.png`, `_ledger_dialog.png`, `_today.png`, `_today_dialog.png`, `_forced_{404,409,500}.png` captured at each width.

## Findings

None caused by RACE. Pre-existing 375 overflow listed above (also on MAIN).
