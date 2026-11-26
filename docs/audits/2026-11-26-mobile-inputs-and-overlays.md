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

## Re-check after fix

Change (overrides.css only, below 48rem): `.rd-filters__extra` is one column (from and to stack at full width); `.rd-dialog .rd-fields-row > .rd-field` takes `flex-basis: 100%` (the half-width pairs stack). Vendored rd/css untouched.

New e2e assertion (`tests/e2e/test_mobile_layout.py`): at 375 each visible select, text and date control shows its whole text (canvas-measured width of the selected option, value or placeholder, plus 24px for a date icon, within the content box; scrollWidth <= clientWidth). With the previous CSS the ledger test failed ("f-from needs 120 has 116") and the new-entry tests failed ("field-account_id needs 192 has 98" for "Credit Card Platinum"); with the fix the ledger test and the full file passed on the first run (5 passed) before the account-select assertion was added, which CI (e2e.yml, Chromium) confirms.

1. Ledger from/to: stacked full width; "26/11/2026" and the picker icon fit (assertion passes, was 120 needed vs 116 available).
2. New entry account select and start date: stacked full width in happened, planned and repeats (available width about 280px against 192 needed for the long account name); asserted in the three tab tests.
3. Account new currency combobox: the placeholder sits in a `.rd-fields-row` pair that now stacks, so it gets the full row; not separately asserted (cosmetic).

Verdict after fix: findings 1 and 2 fixed and asserted; 3 fixed by the same rule, not asserted.

## Re-audit 2 (sha 038207e1)

Scope: verify the three findings against fix 472814d7 and check that the broad rule `.rd-dialog .rd-fields-row > .rd-field { flex-basis: 100% }` (below 48rem) regresses no dialog. Run with the frontend-visual-audit skill (Playwright, scratch DB seeded through the app: three accounts incl. "Credit Card Platinum", categories, one transaction, one planned entry, one recurring rule). 18 dialogs/states plus /ledger (filters open, dates filled) and /today, at 1440, 1024, 375 light and 375 dark (the 1440/1024 pass was repeated with the merge-base `overrides.css` served through a route override for the byte compare). Screenshots: `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/MOBILE2/out/{cur,base}__<viewport>__<state>.png`, results `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/MOBILE2/out/results.json`.

Dialogs covered: new entry happened, planned, repeats, repeats with formula and a second component; budget override (scope selector) and its remove confirm; account new, edit, reconcile, delete confirm; category new, edit, archive confirm; edit recurring rule, edit transaction, edit planned, promote planned, override recurring occurrence.

### The three findings

1. Ledger from/to at 375: stacked full width, 311px wide each; `scrollWidth 309 = clientWidth 309` for both with "26/11/2026" and "27/11/2026" filled, picker icon beside the text, font 16px. Resolved (screenshot `cur__375__ledger-filters.png`). At 1024/1440 the two stay side by side at 150px, 13px, unchanged.
2. New entry account and start/date at 375: both full width (327px) in happened, planned and repeats; "Checking" and the long name "Credit Card Platinum" fit (e2e assertion in the item plus the clip probe: 0 clipped values in the three tabs, formula, edit transaction, edit planned, promote). Resolved.
3. Account new currency placeholder at 375: the name/currency pair stacks, the combobox is 327px; "type to filter ISO code…" shows whole (clip probe 0, was "needs 202 has 114" on the pre-item CSS). Resolved. At 1440/1024 the same placeholder still needs 202 of 184 px; that is the unchanged desktop rendering (identical PNGs, below), not part of this item.

### Regression check of the broad fields-row rule (375)

Every dialog with a `.rd-fields-row` now has its pairs at 327/327 (stacked, one per row): new entry 3 tabs and formula, edit recurring, edit transaction, edit planned, promote, account new and edit. Dialog heights grow only by one stacked field row: happened/planned 658 -> 736px, repeats/formula/edit recurring 788 (unchanged, it already scrolled inside the sheet), account new 680 -> 758, account edit 446 -> 524, edit transaction/planned 594 -> 672, promote 356 -> 434. All fit the 812px viewport except repeats/edit recurring (788, same as before), and in every dialog the save button is reachable (`scrollIntoView` puts it fully inside the viewport: saveOk true in all 18 dialogs x 4 viewport/theme runs). Labels share one left edge with their controls in the stacked rows (the 21px label inset is the design's and is identical at 1440 and in the baseline), vertical gaps between stacked fields are the regular 16px, no orphaned empty column or stray gap; the formula component keeps its two-row layout, the budget override scope selector still wraps "this month only" / "every november" in equal columns, delete/archive/reconcile/remove dialogs are unchanged (identical PNGs). Dialogs without a fields-row (budget override, reconcile, category new/edit, delete, archive, override occurrence) are byte-identical to the pre-item layout apart from the 16px font (budget override is 392 -> 354px: fewer wrapped lines).

### Diagnostics (per state; identical at 375 light and dark)

| Scope | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|
| 18 dialogs + ledger + today @ 1440 | 0 | 0 | 0 | 0 | 0 |
| same @ 1024 | 0 | 0 | 0 | 0 | 0 |
| same @ 375 (light and dark) | 0 | 1 on every page: `pre.rd-hero__loaf` (decorative, pre-existing, in the baseline too; ledger filters 0) | 0 | 0 | 0 |

Note: the audit harness counters read 2 console errors and 1 request failure after navigating away from a page quickly in the same Playwright page (an aborted in-flight request), identical in the baseline-CSS run (not CSS-related). Separate runs on the same build and seed data show 0 console errors and 0 failed requests for /today, /ledger (filters open, from and to filled, 1.2s wait), /accounts, and a dialog open and close; the only console errors are the browser's "Failed to load resource" lines for the three forced 404/409/500 below, which are expected.

### 1024 and 1440 unchanged

All 18 dialogs and ledger filters at 1440 are byte-identical PNGs to the merge-base-CSS run; at 1024 all but 3 dialogs (budget override remove, account delete, category archive), ledger filters and today. A pixel diff of those shows only an 8x10px region in the page behind the dialog ("all 3 accounts" vs "all 4 accounts": the account created by the step 3b success save between the two passes) and, in ledger filters, a 4x44px region in the nav column (same data-driven cause); no rule of this change applies at 48rem and above. The geometry numbers (dialog heights, field widths) are equal between the runs at 1440 and 1024.

### Step 3b (re-run at 375)

- Fonts: 0 visible text-like inputs/selects below 16px in every dialog at 375 light and dark (the pre-item CSS had 1 to 8 per dialog).
- Overlap/outside probe over inputs, selects, buttons, segmented groups, "of" labels: 0 in every dialog.
- Real 422 (native validation bypassed) on account new: "Name is required" and "ISO 4217 code required" shown under the fields; category new 422: "Some fields need fixing: Name". Forced 404, 409, 500 on the account create POST: the dialog stays open and a visible alert shows "That item was not found. It may have been removed.", "That item changed in the meantime. Reload and try again.", "Something went wrong on our side. Try again."; no account row was created (0 "Forced" rows). Success save: "Audit Mobile Acct" created, dialog closed, toast "Audit Mobile Acct created", row visible, no duplicate ids, one `#modal-root`.
- Template logic: this item changes CSS and an e2e test only (git diff 4c97e651..038207e1 touches overrides.css, the e2e test and this record), so no arithmetic, float or literal in a template; rendered amounts equal the seeded values (12.34 transaction, 50.00 planned, 500.00 rule, 100.00 opening balance) in the dialogs.

### Observation (low, not blocking; not one of the three findings)

On /ledger at 375 the search field's placeholder "search description..." is cut ("search descripti") at the 16px size (`cur__375__ledger-filters.png`; the filters toggle sits beside it). Entered text scrolls normally; cosmetic. Suggested: shorten the placeholder or let the search column take more of the row at <48rem.

Verdict: the three findings are resolved, no regression from the stacked fields-row rule, five diagnostics clean, desktop unchanged. One cosmetic observation (ledger search placeholder).
