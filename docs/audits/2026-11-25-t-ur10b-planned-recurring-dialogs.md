# Frontend audit: T-UR10 part 1 (UR10b), planned and recurring dialogs, occurrence override, formula cycles

Probe record by the implementer. A visual-auditor runs the full skill afterwards; its section is appended below it.

- Branch: wi/ui/sourdough/UR10b, probed on the working tree after commit d4acd97d. Date: 2026-11-25.
- Tool: Playwright (chromium) against a uvicorn on a scratch DB (migrated, login user seeded, never data/budget.sqlite): account Checking (PLN), categories Fixed Costs, Salary, Taxes, Car and Bank fees (with colours), rules Fixed Costs (277.94, fixed), Salary (10,000.00) and Taxes (19 % of Salary minus 19 % of Bank fees), and a planned item Car (2,239.80). Light and dark, 1440x900, 1024x768 and 375x812: 6 runs. Each state is captured after `dialog[open]` and once `document.getAnimations()` was empty and no `.htmx-request` was running.
- Reference: docs/design/rising-dough-frontend/pages/overlays/edit-planned.html, edit-recurring--fixed.html, edit-recurring--formula.html, edit-recurring--empty.html, edit-recurring--incomplete.html, edit-recurring--picking.html, override--occurrence.html, override--remove.html
- Scripts and raw rows (not committed): /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR10b/audit/{setup_db.py,audit.py,audit-rows.json,summary.py}.

## Routes and states

The dialogs have no menu on the new shell yet (the planned and recurring row menus are T-UR10a), so the edit dialogs open the way a menu will: `htmx.ajax('GET', url, {target: '#modal-root'})` on /today. The override dialog opens through the Upcoming row menu (the link under test, with `hx-select="unset"`).

| State | Route |
|---|---|
| edit-planned | GET /planned/{id}/edit |
| edit-planned-422 | amount 0 saved from that dialog |
| edit-recurring-fixed | GET /recurring/{id}/edit (Fixed Costs) |
| edit-recurring-empty | "formula" chosen on the fixed rule: one empty component, hero shows the dash |
| edit-recurring-incomplete | percent 19 without categories saved (422, formula message) |
| edit-recurring-formula | GET /recurring/{id}/edit (Taxes, two components, hero 1900.00, "-> next amount 1,900.00 PLN") |
| edit-recurring-picking | the category list of component 1 open |
| override-occurrence | /today, Upcoming row menu, "override" (Fixed Costs, November 2026) |
| override-occurrence-422 | amount `1.2.3` saved |
| override-remove | GET /recurring/{id}/overrides/new?occurrence_date=...&remove=1 after saving 199.00 |

## Diagnostics

horizontalScroll, overflowingElements, duplicateIds, consoleErrors and requestFailures over 10 states x 6 runs = 60 rows: horizontalScroll false, duplicateIds 0, consoleErrors 0, requestFailures 0 and brokenImages 0 in all 60. overflowingElements is 0 at 1440 and 1024; at 375 it is 1 in every state: `pre.rd-hero__loaf` of the Today page behind the dialog (right edge 399 px), the known handoff-parity overflow of the hero loaf (derived.md, "Today, hero loaf at 375 px"), not a dialog element. The dialogs themselves (`.rd-dialog`) never leave the viewport.

Console errors: htmx logs `Response Status Error Code 422 from /recurring/formula/preview` for the live preview of an invalid draft (state edit-recurring-incomplete, 3 of 6 runs); the route answers 422 by contract (`test_formula_preview_statuses`), exactly as in the new-entry dialog. Together with the browser's "Failed to load resource ... 422" lines of the form 422 states these are counted as expected 422 responses, not as errors.

| State | 1440 light | 1440 dark | 1024 light | 1024 dark | 375 light | 375 dark |
|---|---|---|---|---|---|---|
| edit-planned | 0 | 0 | 0 | 0 | 1 (loaf) | 1 (loaf) |
| edit-planned-422 | 0 | 0 | 0 | 0 | 1 (loaf) | 1 (loaf) |
| edit-recurring-fixed | 0 | 0 | 0 | 0 | 1 (loaf) | 1 (loaf) |
| edit-recurring-empty | 0 | 0 | 0 | 0 | 1 (loaf) | 1 (loaf) |
| edit-recurring-incomplete | 0 | 0 | 0 | 0 | 1 (loaf) | 1 (loaf) |
| edit-recurring-formula | 0 | 0 | 0 | 0 | 1 (loaf) | 1 (loaf) |
| edit-recurring-picking | 0 | 0 | 0 | 0 | 1 (loaf) | 1 (loaf) |
| override-occurrence | 0 | 0 | 0 | 0 | 1 (loaf) | 1 (loaf) |
| override-occurrence-422 | 0 | 0 | 0 | 0 | 1 (loaf) | 1 (loaf) |
| override-remove | 0 | 0 | 0 | 0 | 1 (loaf) | 1 (loaf) |

## Screenshots viewed

Under /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR10b/audit/shots/ (60 files named `<scheme>-<width>-<state>.png`). Viewed: light-1440-edit-recurring-formula (band with the signed figure and the next-amount note, category chips, account select, fixed/formula segmented control, two components with sign, percent and category chips, start and stop dates, cadence) and dark-375-override-occurrence (bottom sheet: title, signed hero input with highlight, month stepper, [ save ]).

## Step 3b (probe level)

1. Swap targets: every dialog form posts to its own route and targets `#modal-root` (`hx-post`, `hx-target="#modal-root"`); the hero refresh targets `#modal-root .rd-dialog__hero` (hx-select the same); the formula preview targets `.rd-formula__result` of its own slot; the month stepper links target `#modal-root`. A save answers an out-of-band empty `#modal-root` plus the flash, and the stale events (`forecast-stale`, `ledger-stale`) refetch Today and the ledger; the Upcoming override links carry `hx-select="unset"` so the list's `hx-select` no longer empties the swap.
2. Failing saves: 422 re-renders the dialog with `#error-summary` and the per-field errors, missing fields default to empty text (human messages: "pick a category", "unknown account", "invalid date"); nothing is written (integration tests assert rows and audit count).
3. Templates: no `style=`, no `{% set %}`, no arithmetic or float in `edit-planned.html`, `edit-recurring.html`, `override-occurrence.html`, `override-remove-occurrence.html`, `formula-result.html`; every figure (hero, next amount, month label, remove sentence) is formatted in the view models through `domain.money` and `view_models.month_name`.
4. Money and signs: the hero sign comes from `domain.transactions.signed_legs` via `sign_glyph`; the hero amount is in the rule's or item's account currency; a stored formula cycle falls back to the saved snapshot amount.
5. Rendered equals service: the edit dialogs show the stored amounts (500.00, 2,239.80 as 2239.80), the formula hero equals `formula_svc.preview` (asserted in `test_recurring_dialogs.py`).
6. Scratch data only.

## Open for the visual-auditor

Side-by-side with the handoff at 1440 and 375 (sign glyph weight in the formula hero, chip colours, the stepper arrows), the picking state once the picker is open on a populated list, and the wording "Remove override?" for the occurrence removal. Known deviations are in docs/plans/ui-redesign/derived.md (T-UR10 rows).

## Probe result

Probe: 0 on every diagnostic except the Today loaf behind the dialog at 375 (accepted handoff parity); no findings.
