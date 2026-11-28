# Frontend audit: FORM, one formula message at a time (T-UR58)

Branch wi/ui/sourdough/FORM at d7f44e08, run with the frontend-visual-audit skill (Playwright, scripted
journeys in the session scratchpad), scratch DB (copy of data/demo.sqlite, migrated, login seeded), never data/budget.sqlite.
Screenshots: /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/form-audit/shots/{1440,1024,375}_*.png (viewed: 1440 edit-recurring percent step, 375 failed save step).

## Routes x viewports

Routes: /ledger new entry -> repeats -> formula (steps S1-S5) and the edit-recurring dialog /recurring/16/edit (S6).

| Route / step | 1440 | 1024 | 375 |
|---|---|---|---|
| new entry formula (S1-S5) | hs=false overflowing=0 dups=0 reqfail=0 | hs=false overflowing=0 dups=0 reqfail=0 | hs=false overflowing=2 (pre-existing, see below) dups=0 reqfail=0 |
| edit-recurring formula (S6) | hs=false overflowing=0 dups=0 reqfail=0 | same | hs=false overflowing=1 (pre-existing) dups=0 reqfail=0 |

consoleErrors per viewport run: 22 at each (S1-S6); all are either
`htmx:oobErrorNoTarget, #field-formula-error` (finding F1, 21 per run) or the browser's
"422 Unprocessable Entity" resource line for the preview/save 422 (expected by design, swapped on purpose).
No other console error, no pageerror, no 5xx.

375 overflowing elements (horizontalScroll stays false): `a.rd-tabs__tab` and `label.rd-chip-option`
(scrolling tab and chip rows) and `pre.rd-hero__loaf` on the Today page behind the edit dialog. This change
touches no CSS or layout template, so these are pre-existing (formula row at 375 left to item MOBILE).

## Step 3b

- Swap target: `.rd-formula__result` exists exactly once. No float, /100, *100 or set in formula-result.html or formula.html.
- Number equals the service: + 10% of Side Income previews 76.48 PLN = service 7648; "-10% Side Income + 50% Subscriptions" 3.44 PLN = service 344; save closes the dialog, flash "Recurring rule saved", rule listed in /ledger?view=recurring.
- Sign: "-" on component 0, then "+ add component": component 0 still "-", preview 3.44 (correct).
- Empty sources (Groceries): exactly one message "the picked categories have no recurring amounts in November 2026: a formula reads recurring rules". Failing save: one line (field-formula-error). Editing the percent after it: one line. Incomplete draft: hero note only ("formula needs at least one term"); its failing save: the two field errors, no duplicate.
- Forced 404/409/500 on POST /recurring: dialog stays open with a visible error line each time.
- Hx-trigger events: none added.

## Findings (blocking)

- F1 Behavior, console error: every formula preview response whose page has no failed-save line logs
  `htmx:oobErrorNoTarget, #field-formula-error` (formula-result.html:18, hx-swap-oob="delete" on a missing id). consoleErrors > 0 on every preview.
- F2 Behavior, one-message rule broken in the edit-recurring dialog: its failed-save line has id `field-formula`
  (edit-recurring.html:62), the oob delete targets `field-formula-error`, so after a failing save and a percent edit two identical
  lines show (S6-edit-percent, 1440/1024/375, shot 13_edit_percent.png). Fix: id="field-formula-error" there.
- F3 Behavior, start next month ignored by the live preview: new entry, source Car (yearly rule starting 2027-03-10), start 2027-03-10:
  preview stays "no recurring amounts in November 2026" (even after retyping the percent; request carries start_date=2027-03-10)
  while the service value for March 2027 is 40568 and the save stores 40568 (rule 40). routers/recurring.py formula_preview passes
  today_for(request) instead of formula_svc.evaluation_month(parse_date(start_date), today) (entry_forms.py:548 and recurring_forms.py:250 do).
  The start field also does not retrigger the preview (it sits outside #formula-slot).

## Re-check after fix (FORM)

- F1: the formula error line is now always in the DOM (`#field-formula-error`, hidden when empty) and the preview empties it with `hx-swap-oob="outerHTML"`. Verified by the integration tests (the slot exists once, hidden, in the dialog; the preview answer carries the outerHTML swap) and by the e2e harness, which now fails any test on `htmx:oobErrorNoTarget` (tests/e2e/conftest.py), all four formula e2e journeys green.
- F2: edit-recurring uses the same slot macro (`formula_error_slot`), so the id is `field-formula-error` there too; the integration test of the failing edit save asserts one such element and the error text.
- F3: `formula_preview` passes `forms.evaluation_day(form, today)`; the start field now also triggers the preview (and the hero) in both dialogs. Verified by the integration test (start next month: 200, "1,000.00 PLN"; start today: 422) and the e2e journey: changing only the start date to the source's month turns "no recurring amounts" into "500.00".

## Re-audit 2 (sha df36900a)

Same skill run, scratch DB (fresh copy of data/demo.sqlite, migrated, login seeded), 1440/1024/375, new entry -> repeats -> formula (S1-S5) and /recurring/16/edit (S6), plus S7 (/recurring/17/edit, start date only) and a start-next-month save in S4. Screenshots: /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/form-audit2/shots/{1440,1024,375}_*.png (viewed: 375 edit percent step, one message).

| Route / step | 1440 | 1024 | 375 |
|---|---|---|---|
| new entry formula (S1-S5) | hs=false overflowing=0 dups=0 consoleErrors=0* reqfail=0 | same | hs=false overflowing=2 (pre-existing tabs/chips scroll rows) dups=0 consoleErrors=0* reqfail=0 |
| edit-recurring formula (S6, S7) | hs=false overflowing=0 dups=0 consoleErrors=0* reqfail=0 | same | hs=false overflowing=1-2 (pre-existing) dups=0 consoleErrors=0* reqfail=0 |

*0 apart from the browser's "422 Unprocessable Entity" resource line for the preview/save 422 answers (expected, swapped on purpose; 22 per run). No `htmx:oobErrorNoTarget` (was 21 per run), no pageerror, no 5xx, no other console line.

- F1 fixed: oob console errors 0 at all three widths over the full scenario (preview, failing save, edit percent, success save).
- F2 fixed: after failing save + percent edit exactly one formula message in the new-entry dialog (S3) and in edit-recurring (S6), at all three widths.
- F3 fixed: Car 10% with the start date changed alone to 2027-03-10 (no other input): preview goes from "no recurring amounts in November 2026" to "next amount 405.68 PLN" in both dialogs (S4, S7). Saving S4 stores rule amount 40568 minor = 405.68 PLN, equal to the preview and the earlier service value for March 2027.
- Unchanged checks: sign kept on add component (c0 "-", 3.44 PLN); Side Income +10% 76.48 PLN, save closes dialog with flash "Recurring rule saved"; empty-sources wording exact; incomplete draft shows the hero note, its failing save the two field errors.
- Step 3b: no float, /100, *100 or set in the formula templates (rg); swap target exists once; no duplicate ids; no new HX-Trigger.

Result: CLEAN.
