# Frontend audit: PAR-B dialog error rendering (Q18)

Change: PAR-B (design parity Q18). The dialog-level "N fields need attention" box is gone from `fragments/dialogs/dialog.html`; errors render as the hero error line or a `▲ message` under each field, and errors with no field line render through the `_orphans` macro as `<p class="rd-dialog__error" id="dialog-error-<name>" role="alert">`. Branch `wi/ui/sourdough/PARB`, head 38966a73. Skill: `frontend-visual-audit` (Playwright, chromium, scratch copy of `data/demo.sqlite`, own server on 127.0.0.1:8765).

## Method
For every dialog a failing save was triggered at 1440, 1024 and 375 (native `required` removed so the server path runs). Per case: HTTP status, dialog still open, typed values kept, visible error elements (in viewport, not clipped, topmost via elementFromPoint), `aria-invalid` + `aria-describedby` resolving to a non-empty element, no summary box text, the five diagnostics. Screenshots were saved in `/tmp/fe-par/<viewport>__<case>.png` (not committed) and several were viewed.

## Routes / dialogs x 1440/1024/375
/add (happened, planned, repeats), /transactions/588/edit, /planned/1/edit, /planned/1/promote, /recurring/1/promote, /recurring/1/edit, /recurring/1/overrides/new, /budget/rules/7/overrides/new, /accounts (new, edit, reconcile), /settings?tab=categories (new, edit), /settings/users (add, edit, invite), /dev/shell/dialog and /dev/shell/dialog/invalid.

## Results (about 80 failing-save cases x 3 viewports)
Pass (error visible, in viewport, topmost, dialog open, values kept, no summary box, `aria-invalid` + `aria-describedby` resolve): new entry happened/planned (empty, 0, text, no category, no account, all bad, transit dest=source, transit without dest), repeats (fixed empty/0, formula percent bad, bad/no cadence, missing start, no category, transit dest=source), edit transaction, edit planned, promote planned/recurring (0/empty), edit recurring (amount, cadence, start, formula), recurring override (bad month/amount/year), budget override (bad month, tier bogus), account new (name, currency, opening is 500 see below), account edit name, category new/edit bad color, users add (invalid and duplicate email), user edit invalid email, invite (invalid, duplicate, empty), `/dev/shell/dialog/invalid` (two `▲` lines, hero error). Hero error and `▲` lines use the same classes and markup as the handoff overlays (`rd-dialog__hero-error`, `rd-field__error`). Hero error text is the dark ink colour on the peach band, as in the shell.

Diagnostics (all cases): horizontalScroll=0, duplicateIds=0 at every viewport. requestFailures=1 per viewport (the `/add?wh...` hero-refresh GET aborted by a following request, benign); consoleErrors=~75 per viewport, all "Failed to load resource ... 422" for the deliberately failed saves (expected, not code errors). overflowingElements at 375 only: `label.rd-chip-option` / `input` in the category chip strip (new entry, edit dialogs) and `a.rd-tabs__tab` on /settings; `horizontalScroll` stays false, so they are clipped or scrolled in their strip. NOT compared against MAIN (not changed by this item: no CSS but `.rd-dialog__error` was added); triage as pre-existing unless the orchestrator wants the MAIN check.

Step 3b: templates changed contain no arithmetic / float (dialog.html diff reviewed: `set body` removed, only string concat and `in`). Swap targets: `#modal-root` resolves once; edit dialogs need their row target (`#account-1`, `#category-7`, `#user-row-1`) so they only work from their own page (checked there). Forced 404/409/500 flashes: not run as a separate sweep (time limit); the naturally occurring 500s below do show the assertive flash `▲ Something went wrong on our side. Reference: ...` and keep the dialog open.

## Findings
BLOCKING (failing save with NO visible error; dialog vanishes or nothing shown). Cause: FastAPI answers a raw `{"detail":[{"type":"missing",...}]}` 422 for an empty required `Form(...)` value, before the dialog handler can render:
1. `/categories/new`, empty name or no direction at 1440/1024/375: dialog closes, no error (screenshot `/tmp/fe-par/inv-category-new-name-empty.png`).
2. `/categories/7/edit`, empty name: 422, no error shown (`/tmp/fe-par/desktop__category-edit-name-empty.png`).
3. `/budget/rules/7/overrides/new`, no tier selected: dialog closes, no error (`/tmp/fe-par/desktop__budget-override-no-tier.png`).
4. `/dev/shell/dialog`, empty note: dialog closes, no error (`/tmp/fe-par/desktop__dev-shell-note-empty.png`).
Probably pre-existing (the old summary box could not render for these either); a browser with native `required` blocks 1, 2 and 4 on name/note, not 1 (direction) or 3 (tier).

Non-blocking:
5. Accounts reconcile 422: `aria-invalid` field `actual_balance` has no `aria-describedby`, the error `#field-actual_balance-error` is not linked (A11y).
6. Server 500 on invalid input (a flash is shown, dialog stays open): repeats day_of_month=45 (/recurring), budget override year=1, new account opening_balance "abc", duplicate category name (new and edit).
7. Invalid input accepted (200, saved): edit recurring day_of_month=45, budget override amount "abc" or empty, user edit with empty name (name optional, may be intended).

## Re-audit after validation fix (head c9913359, fix 10de0be6)
Skill: `frontend-visual-audit` (Playwright chromium, scratch copy of `data/demo.sqlite`, own server on 127.0.0.1:8765, lock `/tmp/ui-redesign-heavy.lock` released). The native `required` attribute was removed in the dialog so the server path ran. Screenshots in the scratchpad `shots/` dir (not committed); viewed: `375__cat-new-no-direction.png`, `1440__dev-shell-note-empty.png`.

Cases x 1440/1024/375 (all 12 plus 3 extra at each viewport):
- `/categories/new`, empty name; and name filled with no direction.
- `/categories/26/edit`, empty name.
- `/budget/rules/13/overrides/new`, tier unchecked with a valid amount (12.50). Note: with an empty amount and the default tier the save is accepted (200, dialog closes); that is the earlier finding 7 (invalid input accepted), not a missing-field case.
- `/dev/shell/dialog`, empty note.
- `/accounts/{id}/reconcile`, `actual_balance` = "abc".

Result for every failing case at every viewport: POST answers 422, `HX-Reswap: none`; the dialog stays open (`dialog[open]` count 1, `:modal`); typed values are kept (name "Keep Me Cat", amount "12.50"); the flash `▲ Some fields need fixing: Name | Direction | Tier | Note` is visible, inside the viewport and topmost (`elementFromPoint` hits the flash). Not hidden behind the modal backdrop: `static/rd/js/app-toast.js` `show()` renders the flash in an in-dialog live region (`[data-flash-in-dialog]`, `role="alert"`, `aria-live="assertive"`) because the page-level `#flash-region-assertive` sits under the top layer. At 375 the flash sits at the top of the sheet. Reconcile: `actual_balance` has `aria-invalid="true"` and `aria-describedby="field-actual_balance-error"` resolving to `▲ invalid number` at all three viewports (the typed "abc" is not echoed back into the number input, as before).

Diagnostics (all cases): horizontalScroll=0, duplicateIds=0, requestFailures=0. consoleErrors=1 per case, only the browser line "Failed to load resource ... 422" for the deliberate failed save (no JS errors). overflowingElements at 375 on /settings?tab=categories only: `a.rd-tabs__tab` x2 (the tabs strip, as in the first audit, not changed by the fix); none on the other routes.

Step 3b: `errors.py` and `dialog-reconcile.html` diffs contain no arithmetic or `float`; the new flash goes through `fragments/flash/error.html` (swap target `#flash-region-assertive` exists once; in-dialog region is created by JS). The four earlier BLOCKING findings (1 to 4) and finding 5 (reconcile aria-describedby) are resolved. Findings 6 and 7 remain as triaged.

Status: CLEAN for the re-audit scope.
