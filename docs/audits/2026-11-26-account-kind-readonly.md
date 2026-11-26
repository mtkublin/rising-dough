# Frontend audit: account kind read-only in the edit dialog (ACCTYPE, T-UR60)

Date: 2026-11-26. Branch wi/ui/sourdough/ACCTYPE at ff2af28f. Run with the frontend-visual-audit skill procedure (Playwright, Chromium) on a scratch DB (migrated, two seeded accounts: Checking asset, Visa liability with limit 5000.00); data/budget.sqlite untouched.

## Change

pages/accounts/dialog-account.html: the edit dialog shows "counts as" as read-only text (rd-field--readonly) with a hidden is_liability value; the new dialog keeps the asset/liability toggle; the server answers 422 with a field error on a kind change.

## Routes

/accounts: states list, edit dialog (asset Checking), edit dialog (liability Visa), edit with empty name (422), rename save, edit with forced kind change (422), new-account dialog, new-account dialog with liability chosen. Each at 1440 / 1024 / 375 (the forced kind-change state at 1440 only).

## Diagnostics (per state x viewport)

consoleErrors is cumulative per viewport page; the increments come only from the two deliberately forced 422 saves (browser logs the failed resource); every state that is not after a forced failure shows 0.

| viewport | state | horizontalScroll | overflowingElements | duplicateIds | consoleErrors (cumulative) | requestFailures | screenshot |
|---|---|---|---|---|---|---|---|
| 1440 | list | false | 0 | 0 | 0 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/desktop__list.png |
| 1440 | edit_Checking | false | 0 | 0 | 0 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/desktop__edit_Checking.png |
| 1440 | edit_Checking_empty_name | false | 0 | 0 | 1 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/desktop__edit_Checking_empty_name.png |
| 1440 | after_rename | false | 0 | 0 | 1 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/desktop__after_rename.png |
| 1440 | edit_Visa | false | 0 | 0 | 1 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/desktop__edit_Visa.png |
| 1440 | edit_Visa_kind_change_422 | false | 0 | 0 | 2 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/desktop__edit_Visa_kind_change_422.png |
| 1440 | new | false | 0 | 0 | 2 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/desktop__new.png |
| 1440 | new_liability | false | 0 | 0 | 2 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/desktop__new_liability.png |
| 1024 | list | false | 0 | 0 | 0 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/tablet__list.png |
| 1024 | edit_Checking | false | 0 | 0 | 0 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/tablet__edit_Checking.png |
| 1024 | edit_Checking_empty_name | false | 0 | 0 | 1 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/tablet__edit_Checking_empty_name.png |
| 1024 | after_rename | false | 0 | 0 | 1 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/tablet__after_rename.png |
| 1024 | edit_Visa | false | 0 | 0 | 1 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/tablet__edit_Visa.png |
| 1024 | new | false | 0 | 0 | 1 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/tablet__new.png |
| 1024 | new_liability | false | 0 | 0 | 1 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/tablet__new_liability.png |
| 375 | list | false | 0 | 0 | 0 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/mobile__list.png |
| 375 | edit_Checking | false | 0 | 0 | 0 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/mobile__edit_Checking.png |
| 375 | edit_Checking_empty_name | false | 0 | 0 | 1 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/mobile__edit_Checking_empty_name.png |
| 375 | after_rename | false | 0 | 0 | 1 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/mobile__after_rename.png |
| 375 | edit_Visa | false | 0 | 0 | 1 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/mobile__edit_Visa.png |
| 375 | new | false | 0 | 0 | 1 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/mobile__new.png |
| 375 | new_liability | false | 0 | 0 | 1 | 0 | /tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/9636d2bf-61b0-42d2-957e-732cfda6a6a7/scratchpad/acctype/out/mobile__new_liability.png |

Totals: horizontalScroll=0 overflowingElements=0 duplicateIds=0 requestFailures=0; consoleErrors=0 outside the forced 422 saves (the cumulative 1-2 are the browser's 'Failed to load resource: 422' for those saves).

## Step 3b

- Edit dialog, asset and liability: counts as is read-only text ('asset' / 'liability'), 0 radios; new dialog: radiogroup 'counts as' with 2 radios. ok
- Liability edit: credit limit field present, visible, value 5000.00 (required server-side, unchanged). Asset edit: credit limit hidden. New dialog with liability chosen: credit limit visible. ok
- Failing save: empty name returns 422 and shows the visible '▲ Name is required' under the field (dialog stays open). Forced kind change (hidden value flipped) returns 422 and shows '▲ can't be changed after the account is created' under counts as, input marked invalid. ok
- Rename saves: 200, dialog closed, row shows 'Checking X', flash '● Checking X saved'. ok
- Template logic: rg for float, / 100, * 100, set blocks in dialog-account.html: none. No money rendered by the template (values come from the view model). ok
- Duplicate ids after the HTMX swaps (edit open, 422 re-render, save): 0. ok

## Screenshots viewed

mobile edit_Visa (read-only counts as, credit limit, hint, no overflow at 375) and desktop edit_Visa_kind_change_422 (field error under counts as); the remaining captures were judged by the diagnostics above.

## Findings

None.
