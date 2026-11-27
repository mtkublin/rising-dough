# Frontend audit: budget override scope on one row (BUDSCOPE)

Date: 2026-11-27. Item BUDSCOPE, branch wi/ui/sourdough/BUDSCOPE, audited sha 130260da. Task T-UR76 (R15).
Run with the frontend-visual-audit skill (Playwright, Chromium), scratch copy of data/demo.sqlite (migrated, login user seeded, category 10 budget default soft-deleted so a "set budget" row exists), 127.0.0.1:8111. data/budget.sqlite untouched. Light and dark (`?theme=`) at each width.

Change: `static/rd/app/overrides.css` only. At width >= 48rem the scope control of the budget override dialog (`.rd-field--seg[aria-labelledby="override-budget-scope"]`) is a nowrap flex row that stretches to the field, options `flex: 1 1 auto; min-width: 0; padding-inline: var(--space-2)`. The <48rem equal-column grid is kept.

## Routes and diagnostics

Columns: horizontalScroll / overflowingElements / duplicateIds / consoleErrors / requestFailures. Identical in light and dark.

| Route / step | 1440 | 1024 | 375 |
|---|---|---|---|
| /plan?tab=budget (page) | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| edit budget dialog (row menu, Big Purchases) | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| set budget dialog (unbudgeted row, button) | false/0/0/0/0 | false/0/0/0/0 | false/0/0/0/0 |
| /plan?tab=year (page) | false/0/0/0/0 | false/20/0/0/0 (a) | false/20/0/0/0 (a) |
| year-cell dialog (shift-click, Jan Big Purchases) | false/0/0/0/0 | false/20/0/0/0 (a) | false/20/0/0/0 (a) |

- (a) `table.rd-year` (12 month columns) inside its own scroller; no page horizontal scroll. Identical with the dialog closed (page row) and open, and recorded as pre-existing T-UR71 in docs/audits/2026-11-26-year-cell-scope.md. The scope selector does not exist on the year page, so the change cannot cause it.

## Scope selector measurements (dialog, per width)

| Width | display | Option tops | Option widths (box / text) | Clipped |
|---|---|---|---|---|
| 1440 | flex, nowrap | 504 / 504 / 504 (one row) | 142/117, 127/101, 189/164 | none (scrollWidth = clientWidth, no ellipsis) |
| 1024 | flex, nowrap | 504 / 504 / 504 (one row) | 142/117, 127/101, 189/164 | none |
| 375 | grid (MOBILE rule kept) | 675 / 675 / 675 | 104/78, 104/55, 104/86 ("every month (default)" and "this month only" wrap to two lines inside their equal column, as designed) | none |

The control spans the field (1440: 484-956 = field; 1024: 276-748 = field; 375: 24-351). Same numbers for edit budget, set budget and the year-cell dialog, light and dark.

## Behaviour checks

- Keyboard: focus on the checked radio ("every month (default)"), ArrowRight moves the selection to "this month only" (wraps), so arrows switch scope; 1440, 1024, 375, light and dark.
- Selected state: filled pill (dark on light theme, light on dark theme), label contrast readable at 1440, 1024 and 375 (viewed).
- Other segmented controls: the forecast horizon control (`.rd-segmented`, 6/12/24/60) is unchanged (flex, wrap, 16px option padding, 199px wide at 1440 and 375). The new-entry dialog tabs (happened / planned / repeats) are unchanged (viewed at 1440). The attribute selector matches only the budget scope field, and /ledger and /settings have no `.rd-segmented`.
- Direct no-JS link of a year cell (`/budget/rules/13/overrides/new?...`) answers 200 with a bare, unstyled fragment (no stylesheet, blank page); unchanged by this item and not a CSS matter (same bare-fragment behaviour noted for other dialogs), not caused by this change.

## Step 3b

- Swap targets: `#modal-root`, `#main`, `#period-budget` each match exactly 1 element on /plan?tab=budget; no duplicate ids after the dialog swap (0).
- Failing saves: POST /budget/rules/13/overrides forced to 404, 409 and 500 at 1440: dialog stays open and a visible toast shows ("That item was not found...", "That item changed in the meantime...", "Something went wrong on our side. Try again.").
- Templates untouched (CSS-only diff); no arithmetic or `float` introduced. Rendered numbers unchanged (hero 604.35 = default 604.35 in the dialog; page values not touched).
- No console errors, no request failures, no failed requests in any step above (the only console-error runs are the forced 404/409/500, not counted).

## Screenshots (viewed)

`/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/bs/shots/`: edit-budget-{1440,1024,375}-{light,dark}.png (viewed 1440 light), set-budget-{...}.png (viewed 375 dark), year-cell-{...}.png (viewed 1024 dark), edit-budget-arrow-{...}.png, page-budget-{...}.png, newentry-1440.png (viewed), fail-{404,409,500}.png.

## Findings

None blocking. Three options on one row at 1440 and 1024 with every label fully visible; 375 follows MOBILE.
