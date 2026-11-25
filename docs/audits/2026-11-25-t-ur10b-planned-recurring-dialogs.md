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

---

# Visual-auditor run (frontend-visual-audit skill, Steps 2-3b)

- Branch wi/ui/sourdough/UR10b, head d494b107. Date: 2026-11-25. Lock /tmp/ui-redesign-heavy.lock taken and released.
- DB: scratch copy built for this run (never data/budget.sqlite, not demo): accounts Checking (PLN), Euro (EUR), Yen (JPY); cached rates EUR->PLN 4.25 and JPY->PLN 0.027 (without them /today answers the 503 "no cached FX rate", ADR-0139: by design); rules Fixed Costs 277.94, Salary 10,000.00, Taxes (19 % of Salary minus 19 % of Bank fees), Rent 850.50 EUR with a stored override of 900.00 EUR on 27 Nov, and a stored cycle pair Cyc A / Cyc B; planned Car 2,239.80 PLN, Gym 45.50 EUR, Gym yen 12,345 JPY.
- Scripts and raw rows (not committed): /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR10b/audit2/{setup_db.py,visual.py,behave.py,rows.json,behave.log}. Screenshots: /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR10b/audit2/shots/<scheme>-<width>-<state>.png (102) plus 3b-forced-{500,404,409}.png; handoff renders under /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR10b/audit2/handoff/<name>__<1440|375>.png.
- Opening: edit dialogs through `htmx.ajax('GET', url, {target: '#modal-root'})` on /today; override dialogs and the stored-cycle Today rows through the real Upcoming row menu ("override" link).
- Capture rule: after `dialog[open]` and once `document.getAnimations()` was empty and no `.htmx-request` ran.

## Diagnostics (17 states x 3 widths x light and dark = 102 rows)

States: today-cycle (/today with a stored cycle), edit-planned (PLN), edit-planned-422 (amount 0), edit-planned-eur, edit-planned-jpy, edit-recurring-fixed, edit-recurring-422 (amount 0), edit-recurring-eur, edit-recurring-empty, edit-recurring-incomplete (422), edit-recurring-formula, edit-recurring-picking, edit-recurring-cycle-422 (formula reads its own category), override-occurrence-new (Today link, Fixed Costs), override-occurrence-422 (amount 1.2.3), override-occurrence-existing (Today link, Rent EUR with stored override), override-remove (confirm).

| Width | Rows | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| 1440 (light + dark) | 34 | 0 | 0 | 0 | 0 | 0 |
| 1024 (light + dark) | 34 | 0 | 0 | 0 | 0 | 0 |
| 375 (light + dark) | 34 | 0 | 34 (1 per row: `pre.rd-hero__loaf` of Today behind the dialog, right 399 px; accepted, derived.md "Today, hero loaf at 375 px") | 0 | 0 | 0 |

Expected 422 responses (and their browser "Failed to load resource ... 422" lines, plus the htmx 422 log of the live formula preview of an invalid draft) are not counted as errors, as in the probe. No dialog element overflows at any width.

## Handoff comparison (side by side, 1440 and 375)

Compared edit-planned, edit-recurring--fixed/--formula/--empty/--incomplete/--picking, override--occurrence and override--remove with ours (light and dark). Matching: band (peach light, orange dark), title "edit recurring rule . Taxes", close button, signed hero with currency, category/account/amount segmented control, formula rows (sign toggle, percent, "of", multi-select chips, remove), start/stop/cadence, month stepper with arrows and "November 2026", [ save ] and cancel, bottom sheet at 375 (docked, rounded top, full-width lime primary in dark), picker panel with filter and checkbox rows (the truncated "filter categorie" placeholder is identical in the handoff). Differences covered by derived.md T-UR10 rows (accepted): single server-owned hero (rows 50, 51), destination-account select for transit (52), stepper links and hidden year/month (53), "Remove override?" wording (54), cycle note on Today (57). Chip colours with data and the unselected "recent" row are scratch-data differences (no recent categories), not template defects.

## Findings

Not accepted by derived.md (all non-blocking, none breaks a diagnostic):

1. **Low-medium, formula hero figure has no thousands separator.** edit-recurring-formula shows the hero `1900.00` while its own note reads "next amount 1,900.00 PLN" and the Today row reads "-1,900.00 PLN" (handoff: "-1,836.93"). Same plain-decimal rendering in the hero input of the fixed state (277.94 is below 1,000, so it is only visible from 1,000 up) and in the planned/override hero (2239.80 for the planned Car, shown as 2300.55 after the edit). The figure is the same service value, only the grouping differs. Screenshot: /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR10b/audit2/shots/light-1440-edit-recurring-formula.png vs /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR10b/audit2/handoff/edit-recurring--formula__1440.png. Category: Content (format via `money` filter, not a template calculation).
2. **Low, the next-amount note sits in the hero band** ("-> next amount 1,900.00 PLN" under the figure); the handoff puts it in the body under "+ add component". Row 50 of derived.md accepts the single server-owned hero but does not name the note position.
3. **Low, confirm dialog "Remove override?" is 440 px wide**, handoff 520 px, and "keep" shows no initial focus ring (handoff autofocus on keep). It is the shared confirm variant (T-UR04e), not specific to UR10b. Screenshot: /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR10b/audit2/shots/light-1440-override-remove.png.
4. **Info, cycle 422 hero shows the placeholder dashes** instead of the stored amount while the field error is displayed ("a formula cannot reference its own category"), as for the empty and incomplete states (known probe behaviour).

No Layout, Behavior or Template-logic finding.

## Step 3b (run on a fresh copy of the scratch DB at 1440, light)

1. Swap targets: dialogs post to and swap into `#modal-root`; no duplicate id after open, 422 re-render or save (checked after every save below: 0 duplicate ids).
2. Prefill equals the DB: planned amount 2239.80 vs 223980 minor and description "Car"; recurring fixed 277.94 vs 27794; existing override 900.00 vs 90000; remove confirm quotes the rule amount 850.50 EUR (rule default 85050).
3. Saves store exact values and audit them: planned 2300.55 -> amount 230055, audit `update`; recurring fixed 300.10 -> default_amount 30010, audit `update`; formula 19 % -> 20 % -> `coefficient_bps` 2000, audit `update`; new override 199.00 on Fixed Costs -> amount_override 19900, state overridden, audit `create`; existing override 900.00 -> 910.25 -> 91025, audit `update`; removal -> no overridden row, audit `delete`.
4. Failing saves: planned amount 0 ("amount must be positive"), recurring amount 0, override amount 1.2.3 and the cycle (formula reading its own category) all answer 422 with a visible `#error-summary` and field message, the audit_log count and the stored rows unchanged. Forced 500, 404 and 409 on POST /planned/{id}: a visible flash "Something went wrong on our side. Try again.", "That item was not found. It may have been removed." and "That item changed in the meantime. Reload and try again." appears inside the open dialog (the dialog stays open, nothing saved); screenshot /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR10b/audit2/shots/3b-forced-500.png viewed.
5. After a save: `#modal-root` has no open dialog, the flash is visible ("Planned entry saved", "Recurring rule saved", "Override saved . November", "Override removed"), the Today list updates (Car 2,300.55 in the due-today group, Fixed Costs 199.00 after the override), no duplicate ids.
6. Formula next amount: the dialog note "next amount 1,900.00 PLN" equals the Today Taxes row (-1,900.00 PLN, from the formula service); after typing 20 % the live preview reads 2,000.00 and the saved formula holds 2000 bps. The stored cycle Cyc A / Cyc B shows "Cyc A . formula cycle" and "Cyc B . formula cycle" with 0.00 on Today (no 500). EUR hero and the Rent override read in EUR (900.00 EUR, 850.50 EUR); the JPY planned dialog renders without decimals error (diagnostics 0).
7. Templates (rg over edit-planned.html, edit-recurring.html, override-occurrence.html, override-remove-occurrence.html, formula-result.html, fields/formula-component.html): no `float`, no `style=`, no `{% set`, no `/ 100` or `* 100`, no arithmetic in `{{ }}`, no currency or period literal.
8. Console: 0 errors apart from the expected 4xx/5xx of the forced and 422 requests. HX-Trigger: the saves refetched Today (list updated), so the stale events have listeners.

## Result

FINDINGS (all low or informational, no blocking diagnostic): 1 (hero thousands separator), 2, 3, 4 above.
