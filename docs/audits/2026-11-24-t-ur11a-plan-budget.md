# Frontend audit: T-UR11 (budget part), Plan budget tab on the new shell (UR11a)

- Branch: wi/ui/sourdough/UR11a, audited sha e5dffabf. Date: 2026-11-24.
- Skill: frontend-visual-audit (Playwright, chromium), scratch copy of data/demo.sqlite (never data/budget.sqlite), app served from the worktree.
- Reference: docs/design/rising-dough-frontend/pages/plan/budget.html, pages/overlays/period-picker.html, pages/overlays/row-menu--budget.html (rendered side by side at 1440 and 375).

## Routes and states

/plan?tab=budget, themes light and dark, at 1440, 1024 and 375 (6 theme x viewport runs), states per run:
current month (October 2026), previous period arrow (Sep 2026), past month (Mar 2026, 0 spent), future month (Feb 2027), period picker open, row menu open (first row), row menu on an over-budget row (Car), row menu on a no-budget row (Bank Fees).
Over-budget rows (8 in October) and no-budget rows (3) exist in the demo data, so both were covered.
Old hub tabs, diagnostics only, 1440 light: /plan?tab=year, /plan?tab=forecast, /plan?tab=analytics (still the old layout, render, no signals).

## Diagnostics (every row: horizontalScroll=false, overflowingElements=0, duplicateIds=0, consoleErrors=0, requestFailures=0; also 0 HTTP >= 400 and 0 broken images)

| Route / state | 1440 light | 1440 dark | 1024 light | 1024 dark | 375 light | 375 dark |
|---|---|---|---|---|---|---|
| /plan?tab=budget current | 0 | 0 | 0 | 0 | 0 | 0 |
| ... previous period (Sep 2026) | 0 | 0 | 0 | 0 | 0 | 0 |
| ... past month (Mar 2026) | 0 | 0 | 0 | 0 | 0 | 0 |
| ... future month (Feb 2027) | 0 | 0 | 0 | 0 | 0 | 0 |
| ... period picker open | 0 | 0 | 0 | 0 | 0 | 0 |
| ... row menu open (first / over / no-budget row) | 0 | 0 | 0 | 0 | 0 | 0 |
| /plan?tab=year (1440 light) | 0 | - | - | - | - | - |
| /plan?tab=forecast (1440 light) | 0 | - | - | - | - | - |
| /plan?tab=analytics (1440 light) | 0 | - | - | - | - | - |

"0" in a cell means all five signals are zero/false. Raw rows: /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/ur11a/summary.json.

## Screenshots viewed (under /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/ur11a/shots/)

light-1440-current, dark-375-current, light-375-picker-open (full page), dark-1024-row-menu-over, dark-1440-future, light-1440-tab-year; viewport shots of the open states vp-{light,dark}-{1440,375}-{menu,picker} (full-page shots of top-layer popovers are positioned unreliably, so open states were judged on viewport shots); design-{budget,picker,menu}-{1440,375}; override-dialog-1440.
Checked: hero, tabs, period nav, bars (filled, remainder, over, no budget), status column, total row, mobile stacked rows with bottom tab bar, picker anchored under the trigger at 1440 and as the top sheet at 375 (same as design), row menu as popover at 1440 and bottom sheet with grabber and cancel at 375, light and dark contrast.

## Side by side with the design

Markup, class names and layout match the handoff at 1440 and 375, light and dark. Differences, all data or accepted:
- Category chips are grey: the demo categories have NULL colour (design shows data-color chips); the template emits data-color when the filter returns a name, so it is data, not a template defect.
- Picker note reads "oct = 7 oct -> 7 mar" (design: "-> 7 nov"): it is the service value (next_income_date 2027-03-07 in the demo data); other months read correctly (sep -> 7 oct).
- Future month (Feb 2027): most categories show "0.00 / 0.00 left 0.00" (no budget rows of that month in the demo data), service value.
- Accepted as brief states: period links use ?year=&month= (derived.md); the override item opens the old dialog (UR11b); no toast or assertive region yet (UR02b). Confirmed: override opens the old "Override" dialog in #modal-root (1 element before and after, 0 duplicate ids, 0 console errors); ArrowLeft goes to the previous month (?year=2026&month=9).

## Step 3b

1. Swap targets: the only hx-target is #modal-root, exactly one element before and after the swap.
2. Failing saves: the touched templates contain no state-changing form; the override dialog is the old one (UR11b), not in scope.
3. Templates (rg over pages/plan/budget.html, pages/plan/_tabs.html, fragments/plan/budget-hero.html, fragments/rows/budget-line.html, fragments/plan/period-nav.html, fragments/popovers/period-picker.html): no style=, no {% set %}, no float, / 100, * 100, round, no arithmetic in expressions, no literal currency or period strings. Only comparisons: tab == name, remaining_minor < 0 (over/left wording), unbudgeted_committed_minor > 0, over_count == 1 (category/categories plural), all choosing wording, no derived numbers.
4. Money formatting: all amounts go through money_num(base_ccy) (base currency PLN only on this page; non-PLN and JPY are not exercised here, the page is base-currency only).
5. Rendered equals service: for October (current), Sep, Mar and Feb 2027, the hero figure, the note figures (budgeted, spent, committed, over count), every row (category, spent / budget, status text, bar aria-label) and the total row were compared with budget.month_summary_for_picker + view_models.budget_view on the same scratch DB: 76 checks, 0 mismatches. Example (October): hero -1,801.72 = remaining_minor; Car 359.35 / 354.16, over 5.19. The plan page has no per-day figure.
6. IDs and listeners: no duplicate ids after the override swap; no HX-Trigger emitted by the new templates.
7. Scratch data only (copy of data/demo.sqlite).

## Result

CLEAN: all five diagnostics 0 on every route x viewport x theme, Step 3b ok, no findings.
