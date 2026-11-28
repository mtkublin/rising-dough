# Audit: UR07b Today dialogs on the shared dialog shell (2026-11-25)

## Scope

Change: T-UR07b (ADR-0107, ADR-0152). Branch `wi/ui/sourdough/UR07b`, head `b700e1cd`. The new-entry dialog (`GET /add?dialog=1`, tabs happened / planned / repeats), `GET /planned/{id}/promote?dialog=1`, `GET /recurring/{id}/promote?dialog=1`, and the `/transactions/new` shell page. Every state was opened from `/today` (top bar "[ new entry ]", the phone FAB at 375, the upcoming rows' `promote` links).

Run: `frontend-visual-audit` skill (Playwright, Chromium), 1440x900, 1024x768, 375x812, light and dark (colour scheme emulation, theme = system), 6 configurations x 9 states = 54 captures. Each capture waits for `dialog[open]` and `document.getAnimations({subtree:true}).length === 0` (+300 ms) before the diagnostics are read from the DOM and the screenshot is taken. DB: scratch copy of `data/demo.sqlite`, migrated, never `data/budget.sqlite`. Scratch data added: planned items due today (25 Nov) and overdue (20 Nov), recurring rules with pending occurrences (incl. a formula rule), account "Checking EUR" set to EUR (rate 4.25), a JPY account, "Credit Card" as a liability with limit 5,000.00 (over-limit state), cached EUR/JPY rates.

## Diagnostics (five signals)

States: new-happened, new-planned, new-repeats-fixed, new-repeats-formula, new-error (422), new-over-limit, promote-planned, promote-recurring (fixed), promote-recurring-formula. Light and dark gave identical values.

| Route (state) | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /today + new-entry dialog (all 6 new-* states) | 1440 | false | 0 | 0 | 0 (1 in new-error, see note) | 0 |
| /today + promote dialogs (3 states) | 1440 | false | 0 | 0 | 0 | 0 |
| /today + new-entry dialog (all 6 new-* states) | 1024 | false | 0 | 0 | 0 (1 in new-error, see note) | 0 |
| /today + promote dialogs (3 states) | 1024 | false | 0 | 0 | 0 | 0 |
| /today + new-entry dialog (5 new-* states, over-limit +1) | 375 | false | 1 (2 in over-limit), see note | 0 | 0 (1 in new-error, see note) | 0 |
| /today + promote dialogs (3 states) | 375 | false | 1, see note | 0 | 0 | 0 |

Notes:

- consoleErrors: the only entry in any run is the browser's "Failed to load resource: 422 (Unprocessable Entity)" line for the deliberately invalid submit of the new-error state (and the forced 404/409/500 in Step 3b). No `pageerror`, no CSP violation, no htmx:targetError in any state.
- overflowingElements at 375 (`horizontalScroll` stays false, `scrollWidth` = 375): new-entry states list `label.rd-chip-option` (right 434; over-limit also its hidden radio `input`, right 386). They are the "recent" chips inside `.rd-catfield__recent` (`overflow-x: auto`, a sideways scroller exactly as in the handoff phone sheet, which has the same row); not a page overflow. Promote states list `pre.rd-hero__loaf`, the Today hero ASCII loaf behind the dialog: accepted in derived.md ("Today, hero loaf at 375 px", T-UR07), untouched by this branch (no hero or CSS file in the diff).

## Captures

All under the scratchpad `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/shots/` as `<state>__<1440|1024|375>__<light|dark>.png` (for example `new-happened__1440__light.png`, `new-over-limit__375__dark.png`, `promote-recurring-formula__1440__light.png`), handoff renders as `handoff_<overlay>__<1440|375>.png`, Step 3b evidence as `3b_*.png`. Viewed (after the animation): new-happened 1440 light and 375 light, new-planned 1440 dark, new-repeats-fixed and new-repeats-formula 1440 light, new-repeats-formula 375 dark, new-error 1440 light and 375 light, new-over-limit 1440 light, 375 light and 375 dark, promote-planned 1440 light and 1024 dark, promote-recurring-formula 1440 light, promote-recurring 375 dark, plus the handoff renders of new-entry--happened, --planned, --repeats-fixed, --repeats-formula, --error, --over-limit, --phone-sheet, promote--planned, promote--recurring. The other captures were checked through the DOM diagnostics and the dialog geometry (sheet at 375: bottom-docked, top 134 to 24, height = viewport, scrolls inside, no horizontal scroll).

## Handoff comparison (side by side)

Matching: band (peach light, orange dark), title, round close button, hero amount with underline and currency, tab row (happened / planned / repeats, active black light and cream dark), category field (recent chips, "search all N categories"), account + date row, note, cancel + primary action (orange light, lime dark), sheet at 375 (bottom-docked, rounded top, full-width primary). Promote dialogs match promote--planned and promote--recurring: title "promote to actual · <category>" / "promote · <category>", selected hero amount, date + note fields, cancel + [ promote ]. The over-limit line reads "Credit Card · 7,454.74 over the credit limit (2,544.26 left)" in the handoff format (pink, role=alert); the within-limit line uses the handoff "of … left → … after this" wording.

Differences (none is listed in derived.md for T-UR07b, so none is accepted):

1. Repeats tab has no hero (hero = none, plain "amount" field in the body). The handoff repeats-fixed puts the fixed amount in the hero (-35.50) and has no body amount field; repeats-formula shows the formula result in the hero (-774.01 PLN) and a "-> next amount 774.01 PLN" line. Ours shows a bare band with only the title and no next-amount line until categories are chosen.
2. Hero sign: the handoff shows "-" before the amount once a category is selected; ours shows no sign until the server re-renders (422 or promote), so the happened/planned hero reads "9999.00" with an expense category chosen.
3. Error copy: handoff "Enter an amount above 0.00" and "Pick a category"; ours "amount must be a decimal number within range" and "pick a category". Ours also shows an "N fields need attention" summary box (`field_summary`, T-UR34l) that the handoff error board does not have.
4. Recent chips carry no category colour in the scratch data (demo categories have none; data, not template) and none is pre-selected (handoff pre-selects the first, sample data).

## Step 3b (behaviour contract and template logic)

1. Swap targets: `#modal-root` 1, `#credit-line` 1, formula slot `find .rd-formula__result` 1, `#upcoming-list` 1, before and after the tab swaps and the formula toggle. ok.
2. Failing saves (every one shows a visible error, dialog stays open, nothing saved), except finding F1:
   - empty amount: the browser's native "Please fill out this field." bubble on the hero input (htmx does not post); with the browser validation bypassed the server answers 422 JSON, see F1.
   - amount of spaces (happened, planned, repeats-fixed): inline "amount must be a decimal number within range" plus the summary box; "0": "amount must be positive"; "10.555" on EUR: same decimal error.
   - no category: "pick a category" under the picker plus the summary ("Category: pick a category").
   - bad formula (repeats, formula, no terms): "1 field needs attention Formula: coefficient is required for formula rules".
   - promote with a formula that resolves to -15.56 (rule 33, prefill equals the service value): 422 "amount must be positive" visible.
   - forced 404, 409, 500 on POST /transactions and POST /planned/6/promote: flash "That item was not found...", "That item changed in the meantime...", "Something went wrong on our side. Try again." appears, dialog stays open and unsaved (screenshots `3b_forced_*.png`; the flash renders in the page region under the dimmed backdrop, readable but faint, see F9).
3. No arithmetic: `rg` over `pages/entries/*` and the touched `fragments/fields/*` for `float`, `/ 100`, `* 100`, `{% set`, arithmetic on numbers: no hits. Currency literals: none (`PLN`, `EUR`, `USD`, `JPY` not present in the templates).
4. Money formatting: EUR planned item 25.50 and recurring 15.56 print with 2 decimals and "EUR" in the promote hero; a JPY account amount 1500 saves as 1500 (zero-decimal), but the dialog hero keeps "PLN" and "0.00" for JPY and EUR accounts, see F4. Negatives print with U+2212 ("−123.45", "−15.56") in the promote hero; amounts in the Today list also use U+2212.
5. Rendered number equals the service value (scratch DB, service called directly):
   - limit preview Credit Card, Takeaway, 9999.00: page "7,454.74 over the credit limit (2,544.26 left)"; `compute_limit_preview` gives over_by 745474, available_before 254426 (7,454.74 and 2,544.26). Equal.
   - promote planned prefill 123.45, 55.00, 44.00 equals the planned amounts 12345, 5500, 4400.
   - promote recurring prefill 15.56 (rule 32, fixed, 1556) and -15.56 (rule 33, formula; `resolve_rule_amount` = -1556). Equal.
6. After save and promote: happened save of 12.34: POST /transactions answers HX-Trigger balance-stale, forecast-stale, ledger-stale; hero "left to spend per day" 1,243.74 -> 1,231.40 (12.34 less). Planned save adds "audit new planned" to the upcoming list; repeats save adds the rule. Promote planned (44.00): row gone, hero 1,231.40 -> 1,187.40. After each: `#modal-root` empty (length 0), no `dialog[open]`, duplicate ids 0, URL stays /today. Every emitted event has a listener on /today (today-stale / ledger-stale on hero, upcoming-root, upcoming-list); balance-stale, forecast-stale, budget-stale have none on /today (listeners live on other pages, as before).
7. Top bar "[ new entry ]" from /today opens the dialog on /today; `GET /transactions/new` directly loads the shell, the dialog opens and the URL is replaced with /today; a reload then (and after any open) lands on /today with no dialog. Ledger (old shell) keeps its "+ Add" button on `/add?when=happened` (old slide-over, intended).
8. Override links inside the upcoming list (record only, UR10 owns): `GET /recurring/33/overrides/new?occurrence_date=...` answers 200 but nothing opens (`#modal-root` stays empty). The link has `hx-target="#modal-root"` and no `hx-select`, so it inherits `hx-select="#upcoming-list"` from the list container and the dialog markup is filtered to nothing. The `promote` links avoid it with `hx-select="unset"`. Same for the planned row's override/edit links (`/planned/{id}/edit`) if they have no own `hx-select`.
9. Scratch data only (`--db` scratch copy, `BUDGET_ENV=dev`); no write to `data/budget.sqlite`.

## Findings

| # | Category | Severity | Where | Finding |
|---|---|---|---|---|
| F1 | Behavior | medium | POST /transactions, new-entry dialog, 1440 | With the browser's native validation bypassed (novalidate, or any client that posts an empty `amount`), the server answers 422 with FastAPI's raw `{"detail":[{"type":"missing","loc":["body","amount"],"msg":"Field required"...}]}`; htmx swaps it into `#modal-root`, the dialog disappears and the JSON shows as page text, no flash. Spaces ("   ") are handled inline, so only the truly empty string is missing from the `Form(...)` parse. Fix: make the field optional in the route signature and let `parse`/validation emit the field error (as for spaces). `3b_A2.png`, `err_blank-amount-novalidate.png`. Not reachable with the browser's `required` bubble. Other POSTs (planned, recurring) not exercised with an empty amount. |
| F2 | Behavior | low | POST /planned/{id}/promote | Promote with a non-numeric amount ("abc", validation bypassed) is accepted silently and promotes the planned amount (txn 617 = 12345 for "abc"), no error. |
| F3 | Behavior / parity | low | new-entry hero | Hero sign is missing after choosing a category until a server re-render (see Handoff comparison 2). |
| F4 | Template / behavior | medium | new-entry hero | Hero currency label and placeholder stay "PLN" / "0.00" for EUR and JPY accounts (`select account` changes nothing), while the amount is saved in the account's currency (JPY 1500 stored as 1500). A user typing yen sees "PLN". Fix: hero currency from the selected account (`data-currency` on options, or an htmx swap), zero-decimal placeholder for JPY. `3b_jpy.png`. |
| F5 | Layout / parity | low | repeats tab, all viewports | No hero; differs from the handoff repeats overlays (Handoff comparison 1). Brief anticipated; report only. |
| F6 | Behavior | medium (blocking UR10) | Today upcoming list, override links | `hx-select` inheritance breaks the override links, nothing opens (check item 8). UR10 owns it. |
| F7 | Template logic | low (T-UR07, not UR07b) | Today upcoming list | A planned or recurring item on an EUR account prints its native-currency figure with the base label: "audit eur ... Checking EUR  -25.50 PLN", while its promote dialog shows -25.50 EUR; 4.25 rate is cached, so the list is neither converted nor labelled EUR. `_row_view` formats `item.row.amount_minor` with `base_currency`. |
| F8 | Copy / parity | low | 422 messages | See Handoff comparison 3. |
| F9 | A11y surface | low | forced 404/409/500 flash | The flash region sits in the page under the modal backdrop (dimmed, plain text with a × button), visible but not above the dialog (`3b_forced_500.png`). |
| F10 | Accepted (record) | none | 375 | Non-zero overflowingElements are the scrolling "recent" chips row (handoff parity) and the Today hero loaf behind the promote dialog (derived.md); horizontalScroll false everywhere. |

Status: FINDINGS (F1, F4, F6 are the ones to route; F2, F3, F5, F7 to F9 are triage items).

## Re-audit 67d2da1d

Change: the fixes for F1 to F5, F7 to F9 at head `67d2da1d` (branch `wi/ui/sourdough/UR07b`). Run: `frontend-visual-audit` skill (Playwright, Chromium), 1440x900, 1024x768, 375x812, light and dark, 6 configurations x 21 states = 126 captures. Each capture waits for `dialog[open]` and `document.getAnimations({subtree:true}).length === 0` (+300 ms) before the diagnostics and the screenshot. DB: scratch copy of `data/demo.sqlite` (`/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/re/re.sqlite`, never `data/budget.sqlite`): "Checking EUR" set to EUR, a JPY account "Yen Wallet", "Credit Card" limit 5,000.00, daily EUR and JPY rates, planned items due today (PLN, EUR) and overdue, recurring rules (fixed PLN, fixed EUR, formula). Server on 127.0.0.1:8791, heavy lock held and released.

States: today-eur (Today list with an EUR item, no dialog); new-happened-{pln,eur,jpy}-{start,income,expense} (account picked, then Salary, then Groceries); new-repeats-fixed; new-repeats-formula-empty, new-repeats-formula (12% of Subscriptions), new-repeats-formula-eur; new-422-empty-{happened,planned,repeats} (empty amount, validation bypassed with noValidate); promote-planned, promote-planned-422-abc, promote-recurring, promote-recurring-422-abc.

### Diagnostics (126 captures; light and dark identical)

| Route (states) | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /today + new-entry, promote dialogs, today-eur (21 states) | 1440 | false (0 of 42) | 0 | 0 | 0, except 422 lines below | 0 |
| same | 1024 | false (0 of 42) | 0 | 0 | 0, except 422 lines below | 0 |
| same | 375 | false (0 of 42) | 1 in every state (see note) | 0 | 0, except 422 lines below | 0 |

Notes:

- consoleErrors: the only entries in any run are the browser's "Failed to load resource: ... 422 (Unprocessable Entity)" line, once per deliberately invalid request: the 3 empty-amount POSTs, the 2 promote "abc" POSTs, and one in new-repeats-formula (the live formula preview, ADR-0056 §4, answers 422 while the draft is still empty or incomplete; it clears after the percent is typed). No pageerror, no CSP violation, no htmx:targetError. All other states: 0.
- overflowingElements at 375 (horizontalScroll stays false): the same two accepted cases as the first audit, one per state. `label.rd-chip-option` (right 434) in the dialog states is the sideways-scrolling "recent" chips row (handoff parity); `pre.rd-hero__loaf` (right 399) is the Today hero loaf behind the dialog and on today-eur (derived.md, "Today, hero loaf at 375 px"). Neither is touched by this change. 1440 and 1024: 0.

### Checks per finding

- F1/F2 (human 422). Empty amount with validation bypassed: POST /transactions (happened), /planned and the recurring POST each keep the dialog open, the hero keeps its sign and currency, and show "amount must be a decimal number within range" under the hero, the "1 field needs attention" box and no JSON (new-422-empty-*). Promote planned and promote recurring with "abc": 422 with the same copy, dialog open, hero keeps "-abc PLN" (the text is selected by the focus on the error; browser selection, not a style). DB unchanged by these submits. Fixed.
- F3/F4 (hero follows account, category, source). Hero text read from the DOM after each swap: PLN account: "Amount PLN", income category "+ Amount PLN", expense category "− Amount PLN". EUR account: "Amount EUR", "+ Amount EUR", "− Amount EUR". JPY account: "Amount JPY", "+ Amount JPY", "− Amount JPY". The sign comes from the category and the currency from the account in all three viewports. Fixed. (JPY placeholder "0.00": known gap.)
- F5 (repeats hero). Fixed mode: hero holds the input ("− 0.00 PLN", figure typed there saves as default amount; the repeats-fixed screenshot matches the handoff band except the sample value). Formula mode: hero.output "9.80 PLN" with note "→ next amount 9.80 PLN"; on the EUR account "2.31 EUR → next amount 2.31 EUR" (9.80 / 4.25 rate). Empty draft: "— PLN formula needs at least one term". Fixed.
- F7 (Today rows in the account's currency). today-eur lists "audit eur · Checking EUR −25.50 EUR", "audit fixed eur ... −15.56 EUR", "flow ... −9.99 EUR" and the PLN rows with PLN. Fixed.
- F8/F9: derived.md rows only, nothing to render.

### Step 3b

1. Swap targets: `#modal-root` 1 and `#modal-root .rd-dialog__hero` 1 before the hero swap, after the account swap and after the category swap. ok.
2. Failing saves: POST /transactions forced 404, 409, 500: flash "That item was not found...", "That item changed in the meantime...", "Something went wrong on our side. Try again." appears, dialog stays open, nothing saved (`3b_forced_404/409/500.png`). A forced 500 on the hero GET (`/add?hero=1`): the same flash shows; the hero stays at the previous account's currency (JPY while the select reads EUR) until the next change, visible error so not blocking (`3b_forced_hero500.png`).
3. No arithmetic in templates: `rg` for `float`, `/ 100`, `* 100`, `{% set`, `PLN|EUR|JPY|USD` over `pages/entries`, `fragments/fields`, `fragments/dialogs` and `fragments/rows/upcoming-row.html`: no hits except a comment line in dialog.html ("PLN difference" in a docstring). ok.
4. Money formatting by currency: EUR hero "2.31 EUR", EUR list rows with 2 decimals, JPY accounts saved without decimals (1500 stays 1500), "−" U+2212 in the hero. ok.
5. Rendered number equals the service value: hero "3.01 EUR" (new formula rule, 12% of Subscriptions, EUR account, category Other) equals the promote dialog prefill for the saved rule (`resolve_rule_amount`, 3.01) and the stored transaction (301, account 2). Promote prefills 123.45, 55.00, 25.50 equal the planned amounts (12345, 5500, 2550); recurring prefills 15.56 and 3.21 equal the rules (1556, 321). ok. Note: a formula that sources the category its own rule posts to (test data I created by mistake, rules 39/42) makes the hero (draft, includes the existing rule) differ from the saved rule's prefill (excludes itself); and two such rules form a cycle that made GET /today answer 500 (FormulaCycleError). That is service behaviour outside this change (the cycle check is not run against the rule's own category on save); the two rules were deleted from the scratch DB. Record only.
6. IDs and listeners: duplicateIds 0 in every capture and after every save (see flows). No new HX-Trigger events in the diff.

### Save flows after hero swaps (1440 light, 375 dark, 1024 light; each from /today)

| Flow | Result (DB read after the save) | modal-root / dialog[open] / dup ids |
|---|---|---|
| happened, JPY account, Groceries, 1500 | txn account 11 (Yen Wallet), amount 1500 | 0 / 0 / none |
| happened, EUR account, 12.34 | txn account 2 (Checking EUR), amount 1234 | 0 / 0 / none |
| happened, PLN account, 7.50 | txn account 1, amount 750 | 0 / 0 / none |
| happened, amount "250" typed, then account changed to JPY, saved | amount field kept "250", hero "− Amount JPY", txn account 11, amount 250 | 0 / 0 / none |
| planned, EUR, 9.99 | planned account 2, amount 999 | 0 / 0 / none |
| repeats fixed, EUR, 3.21 | rule account 2, default amount 321 | 0 / 0 / none |
| repeats formula, EUR, 12% of Subscriptions (blurred) | rule saved with coefficient_bps 1200, source [6]; hero 3.01 EUR equals the promote prefill and txn 301 | 0 / 0 / none |
| promote planned (123.45 PLN; 55.00; 25.50 EUR) | txn with the planned amount and account, planned row promoted_to_txn_id set | 0 / 0 / none |
| promote recurring (15.56 PLN / EUR, 3.21 EUR) | txn with the rule amount and account | 0 / 0 / none |

Every save closed the dialog, left `#modal-root` empty (length 0), no `dialog[open]`, URL /today, no console error. At 1024 the formula save was rejected once with a visible cycle error (the test-data cycle above) with the dialog open, as it should.

### Screenshots

`/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/re/shots/<state>__<1440|1024|375>__<light|dark>.png` (126), `flow-*__<vp>__<theme>.png`, `3b_forced_*.png`. Viewed: new-happened-jpy-income 1440 light (JPY, "+"), new-repeats-formula-eur 1440 light (formula hero 2.31 EUR with the note), new-repeats-fixed 1440 light (hero input in the band, handoff repeats-fixed compared: handoff has a sample -35.50, same structure), new-422-empty-happened 375 light (hero error line, summary box, sheet), promote-planned-422-abc 1440 light, promote-recurring-422-abc 375 dark, today-eur 1440 light. The remaining captures were checked through the DOM diagnostics and hero text above.

### Findings

| # | Category | Severity | Where | Finding |
|---|---|---|---|---|
| R1 | Behavior | low | repeats, formula mode, hero | The hero re-renders on `change` of the formula slot, which fires on blur, not on typing: after typing "12" the hero still reads "— EUR coefficient is required for formula rules" until the field loses focus (the in-slot preview chip updates live on keyup). The value is correct after blur and equals the service. Suggest adding `keyup changed delay:400ms` to the hero trigger for the formula slot, as the slot's own preview has. |
| R2 | Behavior | low | hero GET fails (500) | The flash shows, the hero stays at the previous currency while the account select shows the new one until the next change. Visible error, not blocking. |

Status: CLEAN for blocking items (diagnostics 0 at 1440 and 1024; at 375 only the two accepted overflowing elements; F1 to F5, F7 to F9 verified fixed; save flows and promote flows correct). R1 and R2 are triage items.
