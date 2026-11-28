# Frontend visual audit: Q1 formula component errors, hidden empty result, chart cap decimals

Item: Q1 (branch wi/ui/sourdough/Q1, audited sha 0c2d4fc2). Skill: frontend-visual-audit (Playwright, python variant).
Data: scratch DB from `tests/visual/handoff_seed.py` (`build_seed`, modifier `recurring-board`), server through
`tests.visual.frozen_server` with the clock frozen at 2026-10-31. Never `data/budget.sqlite`.
Screenshots (scratch, not committed): `<scratchpad>/shots/<viewport>__<state>.png`, all viewed for 1440 and 375 where named below.

## Routes x viewports (1440 / 1024 / 375)

Columns: horizontalScroll, overflowingElements, duplicateIds, consoleErrors, requestFailures.

| Route / state | 1440 | 1024 | 375 |
|---|---|---|---|
| /plan?tab=analytics | false,0,0,0,0 | false,0,0,0,0 | false,0,0,0,0 |
| /ledger?view=recurring | false,0,0,0,0 | false,20,0,0,0 (a) | false,0,0,0,0 |
| /recurring/6/edit (Taxes) complete | false,0,0,0,0 | false,20 (a),0,0,0 | false,1 (b),0,0,0 |
| edit, one component empty (preview hidden) | false,0,0,2 (c),0 | same as above, ce 2 (c) | 1 (b), ce 2 (c) |
| edit, category picker open | 0,0,0,2 (c),0 | 20 (a), ce 2 (c) | 1 (b), ce 2 (c) |
| edit, save attempt 422 | 0,0,0,3 (c),0 | 20 (a), ce 3 (c) | 1 (b), ce 3 (c) |
| edit, comp0 emptied, then refilled | 0,0,0,6 / 8 (c),0 | 20 (a), ce 6 / 8 (c) | 1 (b), ce 6 / 8 (c) |
| /add?when=repeats (formula) | false,0,0,0,0 | false,0,0,0,0 | false,1 (b),0,0,0 |
| /add?when=repeats, formula save attempt | false,0,0,0,0 | false,0,0,0,0 | false,1 (b),0,0,0 |

horizontalScroll is false and duplicateIds is 0 in every row, also after each HTMX swap (preview, 422).

(a) 1024 /ledger?view=recurring: `th`/`td.rd-row__actions` right edge 1058 > 1024. Ancestor `div.rd-table-scroll` has `overflow-x:auto`
(the table scrolls inside its own container; no page scroll). Neither the table nor its CSS is in the Q1 diff.
(b) 375: `label.rd-chip-option` right edge 381 / 405, inside `.rd-catfield__recent` (`overflow-x:auto`, the intended chip scroller). Not in the Q1 diff.
(c) The only console messages are Chromium's "Failed to load resource ... 422" for the formula preview and the save, both deliberate 422
answers in the states that force them. They accumulate per page in the table above; no JS exception (`pageerror`) in any row, 0 on all plain page loads. requestFailures 0 (no 4xx/5xx other than 422, no aborted request).

## What was checked

- Edit dialog, complete: 2 components, result `<output class="rd-formula__result">` visible: "next amount 3,002.00 PLN".
- One component empty: result output is `hidden` (not visible, no gap); exactly one `.rd-formula__result` in the dialog after the outerHTML swap.
- Save attempt: 422, dialog stays open, under Component 2 "Enter a percentage, e.g. 19 or 12.5" and "Pick at least one category"
  (`p.rd-field__error`, ids `...-pct-err` / `...-cat-err`), the percent input and the category trigger carry `aria-invalid="true"` and `aria-describedby`
  pointing at those ids (target exists), focus lands on the first invalid input. No `role=alert` / `aria-live` element in the dialog (see finding 1).
- Refilled component: preview reappears (one output, visible).
- /add?when=repeats, formula, no category picked: "Pick a category" (page-level). With a category picked and empty component: both component errors
  visible, `components[0][percent]` and the msel trigger `aria-invalid`, result output hidden.
- /plan?tab=analytics 1440: income vs expense chart, bar caps (rounded tops, incl. the outlined expense bars and the orange period bars) intact, no clipped arcs, axis labels fine.

## Step 3b

1. Swap targets: `hx-target="find .rd-formula__result"` matches exactly 1 element before and after the preview swap (outputs count 1).
2. Failing saves (page.route on POST /recurring/6): 404 shows "That item was not found...", 409 "That item changed in the meantime...", 500 "Something went wrong on our side..."; dialog stays open, nothing looks saved. 422 shown per component (above).
3. Templates: `git diff ui/sourdough...HEAD` over `*.html` and `*.js`: no `float`, `/ 100`, `* 100` or `{% set %}` added. OK.
4. Money formatting: not touched by the change (strings come from the view model).
5. Rendered number vs service: see finding 2 (3,002.00 in the dialog against 3,080.65 on the board for the same rule).
6. Listeners: no HX-Trigger event added or removed by the diff.
7. Scratch data only.

## Findings

1. A11y (advisory): the result `<output>` is now replaced with `hx-swap="outerHTML"`; the element carries no explicit `role`/`aria-live` and a replaced live region is generally not announced, so a screen reader will not read the "next amount" appearing. Hidden to visible toggling is by node replacement, not attribute change. Triage: decide whether to add `role="status"` on a stable wrapper (swap innerHTML of a stable `output`, toggle `hidden` on it) or accept.
2. Template logic / numbers (needs the implementer or orchestrator to confirm, not caused by the diff): for rule 6 (Taxes) the dialog preview and hero show `3,002.00 PLN`, while the ledger recurring board row and its formula line show `3,080.65 PLN` at the same frozen date. The Q1 diff does not touch the computation; not compared with `main` in this run.
3. Overflow items (a) and (b) are contained inside scrollers and in files Q1 did not touch; listed for the orchestrator to confirm as pre-existing on main (not checked here).
