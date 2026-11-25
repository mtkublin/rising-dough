# Audit: UR09b edit-transaction dialog on the shared dialog shell (2026-11-25)

## Scope

Change: T-UR09b (ADR-0107, ADR-0152). Branch `wi/ui/sourdough/UR09b`. `GET /transactions/{id}/edit` (dialog, hero refresh with `hero=1`, plain-load shell page), `POST /transactions/{id}` (save, 422), `POST /transactions/{id}/delete` (undo toast). Template `fragments/dialogs/edit-transaction.html` and shell page `pages/entries/open-edit.html`.

Probe: Playwright (Chromium) against the e2e live server with a scratch DB (never `data/budget.sqlite`), 1440x900, 1024x768, 375x812, light and dark (colour scheme emulation), 7 states x 6 configurations = 42 captures. Every capture waits for `dialog[open]`, kills animations and transitions, then waits 400 ms before the diagnostics are read from the DOM and the screenshot is taken. Seeded: accounts Checking (PLN), Savings (PLN), Euro (EUR), Yen (JPY); expense category Groceries, income Salary, the seeded transit; one transaction per state (35.50 PLN, 123.45 EUR, 5000 JPY, a 21.93 transit to Savings). Opened through the transaction's own URL (the plain load: the shell page asks the route for the dialog), so the ledger page itself (T-UR09a) is not part of this record.

The final visual-auditor pass runs after the merge with T-UR09a.

## Diagnostics (five signals)

States: normal (PLN), eur, jpy, transit, error (422 after saving 0), picker (search panel open), no-match (search "zoo"). Light and dark gave identical values.

| Route (state) | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /transactions/{id}/edit (7 states) | 1440 | false | 0 | 0 | 0 (1 in error, see note) | 0 |
| /transactions/{id}/edit (7 states) | 1024 | false | 0 | 0 | 0 (1 in error, see note) | 0 |
| /transactions/{id}/edit (7 states) | 375 | false | 0 | 0 | 0 (1 in error, see note) | 0 |

Note: the only console entry is the browser's "Failed to load resource: 422 (Unprocessable Entity)" line for the deliberately invalid save of the error state. No `pageerror`, no CSP violation, no htmx target error.

## Captures

Under the scratchpad `/private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR09b/` as `<state>__<1440|1024|375>__<light|dark>.png`, diagnostics in `diag.json`. Viewed: normal 1440 light (band, hero `-35.50` with PLN, recent chips with the checked category, search button, account, date and note, cancel and `[ save ]`), transit 375 dark (bottom sheet, arrows sign, 21.93, account next to destination, lime primary).

## Handoff comparison

Matching: band and title (`edit transaction · <category>`), hero amount with sign and currency, category field (recent chips, `search all N categories`), account row, date and note row, cancel + `[ save ]`, the transit variant (arrows sign, destination field shown), the 422 hero error, the phone sheet at 375.

Differences (all listed in `docs/plans/ui-redesign/derived.md`, T-UR09b): no delete button in the dialog (handoff has none; delete stays in the row menu and answers with the undo toast); posted field names are the route's, labels are the handoff's; the plain page load replaces the URL with `/today`. Open: at 375 the account select next to the destination is narrow (`Checki▾`), the same two-column row as the handoff transit variant.

## Behaviour contract (step 3b)

- Prefill is the service value in the account currency: 35.50 PLN, 123.45 EUR, 5000 JPY (integration tests pin the strings).
- Failing saves (empty post, amount 0, bad date, transit without or with a wrong destination) answer an HTML 422 with the summary and per-field errors, keep the posted values, write nothing (rows and audit asserted).
- Swap targets: the form posts to `#modal-root` (innerHTML); a save answers an empty body, the out-of-band `#modal-root` clear and `#flash-region` flash, `HX-Reswap: none`, the three stale events, and `HX-Refresh` off the ledger. The hero follows account and category through `GET /transactions/{id}/edit?hero=1` (only `.rd-dialog__hero` is swapped), the credit line through `/transactions/_limit_preview` with the edited id excluded.
- No arithmetic or `float` in the template; every number is the service value.
