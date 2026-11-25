# Frontend audit: T-UR11 (year and overrides), Plan year tab, override dialogs and year-cell editor (UR11b)

Probe record by the implementer (sections up to "Open for the visual-auditor"), followed by the visual-auditor's skill run ("Visual-auditor audit" below).

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

## Probe result

Probe: 0 on every diagnostic, no findings.

## Visual-auditor audit (frontend-visual-audit skill, 2026-11-25)

- Branch wi/ui/sourdough/UR11b at a78480cf. Scratch DB: a copy of data/demo.sqlite (migrated, login user seeded) plus four categories added through the app's own routes: AuditDefault (default 400.00), AuditEvery (default 300.00, every-June override 450.00), AuditOne (default 200.00, one-off Aug 99.50, one-off Oct 0.00), AuditNone (no budget). Never data/budget.sqlite.
- Tool: Playwright chromium against a uvicorn on the scratch DB, light and dark, 1440x900, 1024x768, 375x812. Every state captured after `dialog[open]` (or `:popover-open`), `document.getAnimations()` empty and no `.htmx-request`.
- Scripts and raw rows (not committed): /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/ur11b-audit/audit.py, audit-rows.json, step3b.py, step3b.json.

### Routes x viewports

| State | Route |
|---|---|
| year-grid | /plan?tab=year&year=2026 |
| year-picker-open | /plan?tab=year&year=2026, picker open |
| year-grid-next | /plan?tab=year&year=2027, reached by clicking 2027 in the picker |
| dialog-month | override dialog, AuditOne Aug (one-off), scope "this month only" |
| remove-confirm | "remove override" from that dialog (override-remove.html) |
| dialog-every | AuditEvery Jun, scope "every june" |
| dialog-default | same dialog, scope "new default" |
| override-422 | amount `1.2.3` saved from that dialog |
| unbudgeted-new-default | disclosure chip AuditNone, opens on "new default" |
| budget-row-menu | /plan?tab=budget&year=2026&month=8, AuditOne row menu open |
| budget-menu-dialog | the menu's "override" item, dialog open |

### Diagnostics

11 states x 3 viewports x 2 schemes = 66 rows, all with horizontalScroll=false, overflowingElements=0, duplicateIds=0, consoleErrors=0, requestFailures=0 (brokenImages=0 too). Overflow ignores elements inside `.rd-table-scroll` (the year grid scrolls sideways inside its own region at 375) and closed popovers. The deliberate 422 of the override-422 state (its console "Failed to load resource" line and response) is excluded and counted as expected; every other HTTP >= 400 and every requestfailed is counted.

| State | 1440 light | 1440 dark | 1024 light | 1024 dark | 375 light | 375 dark |
|---|---|---|---|---|---|---|
| year-grid | 0 | 0 | 0 | 0 | 0 | 0 |
| year-picker-open | 0 | 0 | 0 | 0 | 0 | 0 |
| year-grid-next | 0 | 0 | 0 | 0 | 0 | 0 |
| dialog-month | 0 | 0 | 0 | 0 | 0 | 0 |
| remove-confirm | 0 | 0 | 0 | 0 | 0 | 0 |
| dialog-every | 0 | 0 | 0 | 0 | 0 | 0 |
| dialog-default | 0 | 0 | 0 | 0 | 0 | 0 |
| override-422 | 0 | 0 | 0 | 0 | 0 | 0 |
| unbudgeted-new-default | 0 | 0 | 0 | 0 | 0 | 0 |
| budget-row-menu | 0 | 0 | 0 | 0 | 0 | 0 |
| budget-menu-dialog | 0 | 0 | 0 | 0 | 0 | 0 |

### Screenshots viewed

Under /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/ur11b-audit/shots/ (66 files named `<scheme>-<width>-<state>.png`, plus flash-after-save-1440.png). Viewed: light-1440-year-grid, light-1440-dialog-month, light-1024-year-picker-open, dark-375-override-422, dark-1440-remove-confirm, light-375-unbudgeted-new-default, light-375-budget-menu-dialog, flash-after-save-1440. Handoff references rendered from docs/design/rising-dough-frontend/pages (year.html, override--budget-month, override--remove) under /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/ur11b-audit/ref/.

### Side-by-side with the handoff (1440 and 375)

Same shell, plan tabs, period nav (year picker as a three-year list), legend, grid cell grammar (default, "recurring" glyph and one-off dot with border), hero band with the large amount, "default 200.00" note, scope segmented control ("this month only / every august / new default"), cancel / save actions, bottom sheet at 375, and the remove confirm copy ("<category> · <month> goes back to the default 200.00 PLN.", keep / remove). Accepted differences, all listed in docs/plans/ui-redesign/derived.md T-UR11b rows: no row or column totals, unbudgeted categories are links (the handoff shows plain chips; heading "N categories without a budget"), the radio group is named `tier`, a "remove override" action and the one dialog serving month / every / default / year cell. Not compared: category chip colours (the scratch categories have no colour; coloured demo chips render in the same grid); the handoff's "keep" button shows a focus outline that ours has not at rest (focus state only).

### Step 3b

1. Swap targets: every `hx-target` on the year page (`#main`, `#modal-root`) matches exactly one element before and after the saves; the budget and year pages carry the `budget-stale from:body` listener (target and select `#main`), the only emitter is `override_dialogs` (and the older budget routes). OK.
2. Failing saves: bad amounts `1.2.3`, `1..5`, `12.345` re-render the dialog with `#error-summary` ("1 field needs attention", link "Amount") and the hero error, dialog stays open; budget_one_off_overrides, budget_recurring_overrides, budget_defaults row counts, all stored amounts and audit_log count are unchanged. A forced 404, 409 and 500 on the POST each show a visible alert ("That item was not found...", "That item changed in the meantime...", "Something went wrong on our side...") with the dialog still open and nothing written. GET of an unknown category answers 404 `not found` and opens nothing. OK.
3. Templates (`rg` over pages/plan/year.html, rows/year-grid-row.html, rows/year-cell-editor.html, dialogs/override-budget.html, dialogs/override-remove.html): no `{% set %}`, no `style=`, no `float`, no `* 100` or `/ 100`, no arithmetic. OK.
4. Money formatting: figures come from `domain.money` through the view model (cells, hero, remove sentence). Currency here is PLN only on the scratch DB (the pages show the base currency).
5. Values equal the service: 84 cells (AuditEvery, AuditOne, AuditDefault, Groceries, Travel, Subscriptions, Nights Out x 12 months) compared with `services.budget.yearly_grid` formatted by `format_figure`, 0 mismatches, including recurring (AuditEvery Jun 450.00), one-off (AuditOne Aug 99.50, Oct 0.00, a zero override), default and the demo one-offs (Travel Sep, Nights Out Oct, Subscriptions Oct); `data-state` equals the service origin. The budget tab AuditOne Aug row reads "0.00 / 99.50 left 99.50", equal to the grid. No ASCII hyphen-minus before a digit on the year page (it prints no signed value).
6. Saving, each scope, DB checked: AuditDefault Mar "this month only" 111.11 -> budget_one_off_overrides (2026, 3, 11111); AuditDefault Apr "every april" 222.22 -> budget_recurring_overrides (month 4, 22222) and no one-off row; AuditNone via the unbudgeted chip (dialog opens on "new default") 333.00 -> budget_defaults 33300, the row appears with 333.00 in all twelve months and leaves the disclosure. After each save: `#modal-root` empty, no open dialog, the flash "<category> budget saved" visible (one visible flash, the shell's live region mirrors it), the cell and `data-state` updated, no duplicate ids; 3 audit rows written. The budget tab for March shows AuditDefault "0.00 / 111.11"; a save from the budget tab row menu (AuditEvery 310.00) reloads `#main` in place and flashes "AuditEvery budget saved".
7. Remove: AuditDefault Mar one-off removal returns the cell to 400.00 (state default), the row is soft-deleted, flash "AuditDefault override removed"; AuditDefault Apr recurring removal returns 400.00; AuditEvery Jun recurring 450.00 removal returns the default 300.00. No duplicate ids after any of these swaps.
8. Console during the 3b run: only the browser's "Failed to load resource ... 422" lines of the deliberate bad-amount saves.

### Findings

- None blocking in the UR11b files. Observations for the orchestrator:
  - Not UR11b (from UR11a, fragments/plan/budget-hero.html): the budget tab hero shows a negative "budget left" as ASCII `-5,678.22` (U+002D) on the scratch DB, not U+2212. Outside the files this item touched; the year page prints no signed amounts.
  - The 422 re-render keeps "remove override" in the actions when the scope radio was switched to "new default" (remove then confirms the override of the chosen month, not the default). Cosmetic; matches the derived "remove only when the chosen month has a stored override" rule, which is evaluated for the opening scope.

## Result

Probe: 0 on every diagnostic. Visual-auditor run: 66/66 rows 0 on all five diagnostics, Step 3b ok. CLEAN.
