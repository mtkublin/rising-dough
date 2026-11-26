# Frontend audit: mobile inputs and overlays (MOBILE: T-UR61, T-UR62, T-UR63)

Date: 2026-11-26. Branch wi/ui/sourdough/MOBILE at bc028de9 (change: `src/budget_planner/web/static/rd/app/overrides.css` only).
Tool: `frontend-visual-audit` skill (Playwright/Chromium, one page per route, 375x812 light + dark, 1024x768 and 1440x900 light).
Data: scratch copy of `data/demo.sqlite` (migrated, login user seeded); never `data/budget.sqlite`.
Baseline: same scratch DB, same browser, `overrides.css` replaced by the merge-base version through request interception; screenshots compared byte for byte.
Screenshots: `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/shots/*.png` (`base_*` = before).

## Routes and dialogs

/today, /ledger (filters expanded), new entry (happened, planned, repeats, repeats with formula and a second component), budget override (/plan?tab=budget, /budget/rules/13/overrides/new), /accounts new, edit and reconcile dialogs, /settings?tab=categories new and edit category, edit recurring rule (/recurring/21/edit).

## Diagnostics (per route x viewport; identical in light and dark at 375)

| Route / dialog | 375 hScroll / overflowing / dupIds / console / reqFail | 1024 | 1440 |
|---|---|---|---|
| today | false / 1 (pre-existing) / 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 | same |
| ledger filters | false / 1 (pre-existing) / 0 / 0 / 0 | same, 0 | same, 0 |
| new entry happened | false / 2 (pre-existing) / 0 / 0 / 0 | 0 | 0 |
| new entry planned | false / 2 (pre-existing) / 0 / 0 / 0 | 0 | 0 |
| new entry repeats | false / 2 (pre-existing) / 0 / 0 / 0 | 0 | 0 |
| new entry formula (2 components) | false / 2 (pre-existing) / 0 / 0 / 0 | 0 | 0 |
| budget override | false / 0 / 0 / 0 / 0 | 0 | 0 |
| account new | false / 0 / 0 / 0 / 0 | 0 | 0 |
| account edit | false / 0 / 0 / 0 / 0 | 0 | 0 |
| account reconcile | false / 0 / 0 / 0 / 0 | 0 | 0 |
| category new | false / 2 (pre-existing) / 0 / 0 / 0 | 0 | 0 |
| category edit | false / 2 (pre-existing) / 0 / 0 / 0 | 0 | 0 |
| recurring edit | false / 2 (pre-existing) / 0 / 0 / 0 | 0 | 0 |

Totals: horizontalScroll=0, duplicateIds=0, consoleErrors=0, requestFailures=0 in all 13 scenarios x 4 viewport/theme combinations (52 runs).
overflowingElements: at 375 the same elements overflow on the baseline CSS, byte-identical lists: `pre.rd-hero__loaf` (decorative), `a.rd-tabs__tab` (tab strip that scrolls inside its own container), `label.rd-chip-option` (recent-category chip row that scrolls inside its container). None causes page scroll. Not introduced by this change; triaged as pre-existing.

## Desktop unchanged

All 13 scenarios at 1024 and at 1440 are byte-identical PNGs to the baseline (including /ledger and the new-entry dialog). At 1024/1440 the controls keep their 13/14px sizes (the rule is gated on width < 48rem or a coarse pointer).

## Step 3b (behaviour contract)

- Font size at 375 (light and dark), visible text-like input/select/textarea (checkbox, radio, hidden, button excluded): 0 below 16px in every scenario (field counts: today 1, ledger 6, new entry 4/4/6/7, budget 1, account new 5, edit 3, reconcile 1, category 1, recurring edit 6). Baseline had 1, 6, 3, 3, 5, 7, 0, 4, 3, 1, 1, 1, 5 below 16px respectively. Viewport meta untouched (pinch zoom kept; CSS-only change).
- No overlap or outside-dialog control at 375 in any dialog (overlap probe over inputs, selects, buttons, segmented groups, "of" labels): 0.
- Scope selector (budget override): equal full-width columns; "this month only" and "every october" wrap to two lines, no label truncated (segTrunc 0).
- Formula component: two rows (sign, percent, remove / "of" + full-width category). Category trigger 235px wide; opening it shows the filter box and options inside the dialog. Second component added: same layout, no overlap.
- Swap targets: `#modal-root` and `#account-form` each match exactly one element after the dialog swap; no duplicate ids after any swap.
- Failing saves (account new, 375): real 422 (name and currency empty, native validation bypassed) shows "Name is required" and "ISO 4217 code required"; category new 422 shows "Some fields need fixing: Name"; forced 404, 409 and 500 each leave the dialog open with a visible alert/toast ("That item was not found...", "That item changed in the meantime...", "Something went wrong on our side..."). Success: account "Audit Mobile Acct" saved, dialog closed, toast "created", row visible on the page.
- Template logic: change is CSS-only, no template or view-model touched; no arithmetic, float or literal introduced. Rendered numbers unchanged (desktop screenshots identical; budget dialog hero 604.35 equals "default 604.35" before and after).
- HX-Trigger emitters/listeners: untouched.

## Findings (low severity, layout, 375 only; none blocks the diagnostics)

1. /ledger filters, from/to date inputs: at 16px a filled date ("26/11/2026") is clipped at the end of the year, under the picker icon (control 150px wide, scrollWidth 148 = clientWidth; screenshot `ledger_dates_filled.png`). The empty placeholder shows "dd/mm/yyy". The change fixed the overlap and off-screen run of the two fields but the text does not fit. Suggested: reduce inline padding of `.rd-filters input[type=date]` or stack from/to full width below 48rem. File: overrides.css (the T-UR63 block).
2. New entry (happened / planned / repeats), account select in the half column: "Credit Card" renders as "Credit Car" (value clipped by the caret); start date "26/11/2026" touches the picker icon (`ne-repeats__375_light.png`). Not an overlap, but the label is cut. Suggested: give the account select the wider column or let the date column shrink.
3. Account new dialog, currency combobox: placeholder "type to filter" is clipped to "type to fi" (`acct-new__375_dark.png`). Cosmetic; the entered code (3 letters) fits.

Verdict: FINDINGS (3 minor layout items above, otherwise all five diagnostics clean and desktop unchanged).
