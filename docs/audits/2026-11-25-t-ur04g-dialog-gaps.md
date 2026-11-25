# Probe record: T-UR04g dialog macro gaps (hero placeholder, typing race, action hx attrs, field_error, budget hero sign)

Task: T-UR04g, branch wi/ui/sourdough/UR04g. ADR-0027, ADR-0107, ADR-0130 section 7, ADR-0150.
Method: integration tests plus Playwright e2e against a scratch live server (temp DB; data/budget.sqlite not touched). The multi-viewport
visual sweep (1440/1024/375, light and dark) is the visual-auditor section below.

## Probes run

| Probe | Result |
|---|---|
| New entry, JPY account: hero placeholder | "0" (PLN and EUR keep "0.00"); integration `test_hero_placeholder_follows_the_currency_exponent` |
| Typing during a held hero refresh (account switched to JPY, "1234" typed, refresh released) | the amount stays "1234", unit JPY, placeholder "0", saved amount stored as 1234; e2e `test_amount_typed_during_the_hero_refresh_is_kept_and_stored`; the test fails (empty amount) when the restore handler is disabled |
| Hero refresh answers HTTP 500 | the unit shows an em dash; e2e `test_failed_hero_refresh_marks_the_unit_stale` |
| Formula slot trigger | `keyup changed delay:400ms from:#formula-slot` plus change; refresh uses `hx-sync="closest form:drop"` |
| Budget hero, remaining -567822 PLN | "−5,678.22" with U+2212 (`test_budget_hero_prints_a_negative_left_with_the_display_minus`) |
| Category dialog 422 | name/direction/color error paragraphs from `field_error`, id `field-<name>-error` (existing settings e2e journey passes) |
| Parity of existing dialog callers | dev variants and handoff skeleton tests unchanged and green; action hx-include/hx-vals absent unless given |

## Visual audit (frontend-visual-audit skill, visual-auditor)

Head audited: a13b0b6a. Heavy lock /tmp/ui-redesign-heavy.lock taken and released. Chromium (Playwright), prod CSP, a scratch copy of
data/demo.sqlite (migrated, login user added, an EUR account "Euro Acct" and a JPY account "Yen Acct", cached EUR and JPY rates, an expense
category "Overspend" with a budget of 100.00 and 60,000.00 spent in November so the budget left is negative). data/budget.sqlite not touched.
Each capture was taken after `dialog[open]` and once `document.getAnimations()` was empty.

### Routes and states (18 states x 3 widths x 2 themes = 108 diagnostic rows)

/today (new-entry dialog), /settings?tab=categories (category dialog, archive dialog), /plan?tab=year (UR11b override dialog),
/dev/shell (dialog variants standard, confirm, blocked, sheet, invalid, reconcile), /plan?tab=budget.

| State | What was done |
|---|---|
| dlg-new-entry-open, dlg-happened-pln / -eur / -jpy | open, pick category, switch account PLN, EUR, JPY; hero placeholder and unit read from the DOM |
| dlg-typing-after-pick | refresh held, "1234" typed during the refresh, refresh released |
| dlg-hero-fail | hero refresh answered 500 by route interception |
| dlg-new-entry-422 | amount typed, no category, save |
| dlg-repeats-formula-typing | repeats tab, formula, category ticked, "15" typed in the percentage field without leaving it |
| dlg-category-422 | new category with a blank name |
| dlg-archive, dlg-override, dlg-dev-* | regression parity of the unchanged dialogs |
| plan-budget | /plan?tab=budget with a negative budget left |

### Diagnostics

| Rows | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|
| 102 of 108 (every state except dlg-happened-pln), 1440 / 1024 / 375, light and dark | 0 | 0 | 0 | 0 | 0 |
| dlg-happened-pln, all six width x theme rows | 0 | 0 | 0 | 2 | 1 |

HTTP answers of 422 (new-entry, formula preview, category, dev invalid) and the forced 500 of the hero refresh are deliberate and not counted.
A 503 on /today seen in an early run was the scratch DB lacking cached EUR and JPY rates for the new accounts (ADR-0139); fixed in the scratch data.

### Placeholder, unit and the failure mark

| State | Result |
|---|---|
| PLN | placeholder "0.00", unit PLN |
| EUR | placeholder "0.00", unit EUR |
| JPY | placeholder "0", unit JPY |
| hero refresh 500 | unit shows an em dash, typed 1234 kept, red flash above the dialog |
| repeats, typing in the percent field | exactly one hero request fired by keyup (400 ms), focus stayed in the field; the hero text changed with the result |

### Step 3b

- Error ids: new-entry 422 has `catpick-new-entry-error` (the picker's own paragraph, wired by aria-describedby); category 422 has
  `field-name-error` (field_error macro, wired by aria-describedby on the input). Ids unique; duplicateIds 0 on every row.
- 422 summary: links `#field-category_id` (new entry) and `#field-name` (category); both targets exist, on all six rows.
- Budget hero: page text is "−61,701.72" (first character U+2212); the service value (`budget_view_for`, remaining_minor -6170172,
  `format_figure`) is "−61,701.72"; equal. The total row prints "over 61,701.72".
- Templates (dialog.html, field-error.html, budget-hero.html, new-entry.html, category-dialog.html): no `float`, `/ 100`, `* 100`, `style=`
  or `{% set %}` (rg); tests/architecture/test_template_logic.py passes.
- Failing saves: a 500 on the hero refresh and a 422 on both saves show a visible error. 404 and 409 on the save routes were not forced (the
  save routes and their error handling are unchanged by this item).

### Findings (blocking)

| # | Category | Route and state | Problem |
|---|---|---|---|
| F1 | Behavior | new-entry, picking a category through the search box with Enter, all widths and themes | The picker fires two `change` events on `#field-category_id`; with the new `hx-sync="this:replace"` on `#hero-refresh` the first hero request is aborted: requestFailures 1 (net::ERR_ABORTED) and consoleErrors 2 (`htmx:afterRequest`, `htmx:sendAbort`). Clicking a recent-category chip fires one event and is clean. Suggested fix: `hx-sync="this:queue last"` (no abort), or dedupe the double change in the picker. |
| F2 | Behavior | new-entry, amount typed while a hero refresh is in flight (real key presses, not `fill`) | After the restore the amount is focused but fully selected (selectionStart 0, selectionEnd 4 for "1234"; typed_real.png shows the highlighted value). The next key replaces everything: pressing "5" leaves "5". The value survives, but typing cannot continue. The caret should be at the end. In app-toast.js the `htmx:afterSwap` restore should set the selection after htmx's own focus restore (afterSettle or a zero-delay timeout) and collapse it to the saved caret. |

### Regression parity

Unchanged dialogs look as before: dev standard, confirm, blocked, sheet, invalid (422 with two field errors), reconcile, the UR11b override
dialog (hero "100.00" with the "default 100.00" note, scope control, bottom sheet at 375) and the UR13 archive confirm. Handoff renders compared:
overlays new-entry--happened and new-entry--error, new-category--error, plan/budget. Structure (band, hero, error summary above the body, inline
error under the field, actions row) matches; the handoff board draws the dialog over Today and puts the amount error in the hero, while the app
prints the picker error under the field. Autofocus selects the whole amount in the dev sheet, override and 422 re-renders: the shell's designed
behaviour on open.

### Screenshots

In /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/ur04g/shots/ as
`<1440|1024|375>_<light|dark>_<state>.png`, handoff renders as `handoff_<overlay>__<1440|375>.png`, `typed_real.png` for F2.
Viewed: 1440 light happened-jpy, typing-after-pick, new-entry-422, repeats-formula-typing, plan-budget, dev-sheet; 1440 dark category-422;
1024 dark hero-fail; 375 dark hero-fail, category-422, new-entry-422, plan-budget; 375 light override; handoff new-entry--error. The rest were
checked through the DOM diagnostics.

## Re-audit after fixes (head 1a2cfb16, visual-auditor)

Same scratch DB recipe and method as above (fresh copy, heavy lock taken and released). The full 108-row sweep was re-run, plus focused checks
at 1440, 1024 and 375 in light and dark (36 focused runs).

### Diagnostics

| Rows | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|
| all 108 (18 states x 3 widths x 2 themes), including dlg-happened-pln | 0 | 0 | 0 | 0 | 0 |

Step 3b repeated: the new-entry and category 422 error ids are unique and wired, the summary links resolve, and the budget hero still prints
"−61,701.72" (U+2212, equal to the service value) at every width and theme.

### F1 (hero request aborted on a search pick): fixed

| Check | Result at all six width x theme combinations |
|---|---|
| Pick a category with search plus Enter | exactly 1 hero request, 0 console errors, 0 failed requests |
| Blur the search box afterwards | still 1 request (no second refresh from the native change) |
| Pick a recent category by click | 1 hero request, hero refreshed |
| Pick a recent category by keyboard (focus the radio, Space) | 1 hero request, hero refreshed |

### F2 (caret after the hero swap): fixed, one cosmetic note

- Real key presses: click the amount, wait, type "12", hold the refresh (account switched to EUR), release it, then type "34": the value is
  "1234" at every width and theme; unit EUR; the typed value is never lost.
- Fresh focus without a refresh in flight (blur to the note, then `focus()` and then a click on the amount): value "1234", selection 0..4, so
  amount-input's select-all-on-focus still works.
- Caret flicker (the amount sampled every 10 ms across the swap): the selection is 2..2 before the swap, becomes 0..2 (whole value selected)
  for about 20 to 30 ms (two or three samples, one to two frames), then returns to 2..2 and stays. A brief select-all highlight may flash once
  per swap; it never persists and no input is lost. Triaged as cosmetic (low), not blocking.

### Save during an in-flight hero refresh

Refresh held, then [ save ] clicked, at all six combinations: the dialog closes, the transaction is stored (row count 1 for the note, checked
in the scratch DB), and the console shows `htmx:afterRequest` and `htmx:sendAbort` plus one aborted (net::ERR_ABORTED) refresh request. The
save succeeded, so this is expected (the save aborts the stale refresh on purpose, app-toast.js `htmx:beforeRequest`) and recorded as such.

### Regression sweep

The other states from the first pass (dev variants standard, confirm, blocked, sheet, invalid, reconcile; UR11b override; UR13 archive; category
422; new-entry 422; hero fail with the em dash; typing after an account pick; JPY placeholder "0" against "0.00" for PLN and EUR; formula typing;
budget hero) show 0 on all five diagnostics and unchanged screenshots. Viewed: `re_1440_light_typing.png`, `re_375_dark_typing.png`.
Focused results are in scratchpad `ur04g/re.json`.
