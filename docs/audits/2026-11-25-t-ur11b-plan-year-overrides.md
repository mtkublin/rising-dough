# Frontend audit: T-UR11 (year and overrides), Plan year tab, override dialogs and year-cell editor (UR11b)

Probe record by the implementer. A visual-auditor runs the real audit afterwards.

- Branch: wi/ui/sourdough/UR11b, probed on the working tree after commit 660cdaeb plus the base.html script-tag removal. Date: 2026-11-25.
- Tool: Playwright (chromium) against the e2e `live_server` (scratch DB under pytest tmp, never data/budget.sqlite), seeded through the app's own routes: Groceries (default 500.00, one-off 321.00 in March, recurring 700.00 in June), Rent (default 1,200.50, one-off 1,500.00 in October), Gym (no budget).
- Reference: docs/design/rising-dough-frontend/pages/plan/year.html, pages/overlays/override--budget-month.html, override--budget-every.html, override--budget-default.html, override--remove.html, period-picker--year.html, row-menu--budget.html.

## Routes and states

Light and dark at 1440, 1024 and 375 (6 runs). Each state captured after `dialog[open]` (or the popover) and once `document.getAnimations()` was empty.

| State | Route |
|---|---|
| year grid | /plan?tab=year&year=2026 |
| year picker open | /plan?tab=year&year=2026 |
| dialog on this month only, with "remove override" | opened from the March Groceries cell |
| remove confirm | "remove override" in that dialog |
| dialog on every june (recurring, stored 700.00) | opened from the June Groceries cell |
| 422 with the error summary | June dialog saved with amount `1.2.3` |
| budget row menu -> dialog | /plan?tab=budget&year=2026&month=10, Groceries row menu, "override" |

## Diagnostics

All five signals (horizontalScroll, overflowingElements, duplicateIds, consoleErrors, requestFailures) are 0/false in all 42 rows (7 states x 6 runs). Overflow counted elements outside `.rd-table-scroll` whose box leaves the viewport; the year grid scrolls sideways inside its own region at 375. The browser's own "Failed to load resource ... 422" console line of the deliberate 422 state is excluded (the 422 is the tested response, HX-Retarget swaps it in); requestFailures also counts every HTTP >= 400 other than that 422 (none).

| State | 1440 light | 1440 dark | 1024 light | 1024 dark | 375 light | 375 dark |
|---|---|---|---|---|---|---|
| year grid | 0 | 0 | 0 | 0 | 0 | 0 |
| year picker open | 0 | 0 | 0 | 0 | 0 | 0 |
| dialog, this month only (remove offered) | 0 | 0 | 0 | 0 | 0 | 0 |
| remove confirm | 0 | 0 | 0 | 0 | 0 | 0 |
| dialog, every june | 0 | 0 | 0 | 0 | 0 | 0 |
| dialog 422 | 0 | 0 | 0 | 0 | 0 | 0 |
| budget row menu -> dialog | 0 | 0 | 0 | 0 | 0 | 0 |

Raw rows: /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR11b/probe-{light,dark}-{1440,1024,375}.json.

## Screenshots viewed

Under /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR11b/shots/: light-1440-year (grid with the dot and arrow glyphs on the one-off and recurring cells, legend, disclosure "1 category without a budget"), dark-375-dialog-one-off-with-remove (bottom sheet: title, 321.00 hero, "default 500.00" note, scope radios, cancel/remove override/save). All 42 shots exist for the visual-auditor.

## Step 3b (probe level)

1. Swap targets: the year cell and the budget row menu target `#modal-root`; the dialog form posts to the same route and targets `#modal-root`. A save sends `budget-stale`; the hidden listener (`hx-trigger="budget-stale from:body"`, target and select `#main`) reloads the page body. e2e proves the cell text changes after save and after remove.
2. Failing saves: 422 re-renders the dialog with `#error-summary` ("1 field needs attention", link `#field-amount`) and the hero error; nothing is written (integration tests assert DB rows and audit count).
3. Templates: no `style=`, no `{% set %}`, no float or arithmetic in `pages/plan/year.html`, `fragments/rows/year-grid-row.html`, `fragments/rows/year-cell-editor.html`, `fragments/dialogs/override-budget.html`, `fragments/dialogs/override-remove.html`; cell text, glyphs, aria labels, links, scope labels, hero note and the remove sentence come from `web/plan_year_view.py`. Only conditionals are `if` on view-model flags (current month, checked radio, state colour).
4. Money: every figure goes through `domain.money` (`format_figure`, `format_major`); no signed values on these pages.
5. Rendered equals service: the cells equal `budget.yearly_grid` per tier (one-off, recurring, default, zero override); asserted in `tests/integration/web/test_plan_year.py` and `test_plan.py`.
6. Scratch data only.

## Open for the visual-auditor

Side-by-side comparison with the handoff at 1440 and 375, chip colours (the scratch categories have no colour), and the wording of the remove sentence. Known deviations are listed in docs/plans/ui-redesign/derived.md (T-UR11b rows).

## Result

Probe: 0 on every diagnostic, no findings; formal audit pending.
