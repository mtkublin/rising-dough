# Frontend visual audit: T-UR08a accounts page

Task: T-UR08 (page part), branch wi/ui/sourdough/UR08a at 2edc62f4. ADR-0027, ADR-0150.
Method: frontend-visual-audit skill (Playwright, chromium), heavy lock /tmp/ui-redesign-heavy.lock taken and released.
Scratch data only: a copy of data/demo.sqlite (plus two added accounts, Euro Cash EUR and Yen Wallet JPY, with cached FX rates, to
exercise non-PLN and zero-decimal currencies) and a fresh migrated DB for the empty state. data/budget.sqlite not touched.

## Routes

/accounts (populated, 12 accounts incl. a liability with credit limit, accounts with and without "after planned", accounts never
checked, zero-transaction accounts; no archived accounts exist in the demo data), /accounts (empty, fresh DB), /accounts with a row
menu open (first row, and Credit Card row). Light and dark theme, each at 1440, 1024 and 375: each state in light and dark
(24 diagnostic rows: 4 states x 3 widths x 2 themes).

## Diagnostics

| Route / state | 1440 light, dark | 1024 light, dark | 375 light, dark |
|---|---|---|---|
| /accounts populated | hs=0 ov=0 dup=0 console=0 reqfail=0 | same | same |
| /accounts row menu open (2 variants) | same (0/0/0/0/0) | same | same |
| /accounts empty | same (0/0/0/0/0) | same | same |

horizontalScroll=0, overflowingElements=0, duplicateIds=0, consoleErrors=0, requestFailures=0 in all 24 rows (requestfailed plus
HTTP >= 400 responses counted as failures; none). Every id-based hx-target (#modal-root, #account-N) matches exactly one element.

## Comparison with the handoff boards (pages/accounts.html, accounts--empty.html, overlays/row-menu--account.html)

Screenshots of the boards were taken at the same widths and themes and compared with the app. Hero (label, figure, unit, note),
panel head (count caption on phone, + new account), column set and order (account, trend, checked, txns, balance, reconcile, row menu),
phone layout (trend and txns hidden, "checked 01 APR" in the subtitle, balance beside the name, tab bar), credit bar line and wrap,
after-planned note, negative colour, empty state (loaf, message, primary button), dark theme (orange hero, lime accent) and the row menu
(desktop popover with edit and delete, phone bottom sheet with grabber, header, reconcile, edit, delete, cancel) match in structure,
spacing and type.

Known and accepted (confirmed, not findings): sparkline margin by transform and real trend geometry instead of the board's mock
curve; credit-bar aria wording; empty-state hero shows real totals (0.00) instead of the board's populated numbers; checked date or
"never"; the "after planned" note; old dialogs behind new account, reconcile and edit (UR08b); no toast on a failed or successful
delete yet (UR02b).

## Findings

1. Content, low: the account subtitle prints the raw type for liabilities, "credit_card · liability" (1440, 1024, 375, both themes;
   board: "credit card · liability"). Source: web/accounts_view.py account_row, subtitle for liabilities uses acc.type unformatted
   (the other subtitles are single words so are unaffected). Screenshot: /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR08a/shots/demo-light-1440-normal.png.
2. Behaviour, known (UR02b), note for the wave: a failing delete from the row menu is silent. Forced 404, 409 and 500 on
   POST /accounts/11/delete and a real 409 (account 10 has transactions): the row stays, htmx logs the error to the console only, no
   flash or toast is shown. Matches the brief's accepted "no assertive flash region / toast yet"; it must be re-checked when UR02b
   lands. Screenshots: /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR08a/shots/fail-404.png, fail-409.png, fail-500.png, real-delete.png.

## Step 3b

- Templates (pages/accounts/index, fragments/rows/account-row, reconcile-snapshot, charts/sparkline, states/accounts-empty): rg for
  style=, {% set %}, float, / 100, * 100, literal currency codes and arithmetic inside {{ }}: no hits. Amounts only through money_num
  with the row currency (base currency for the hero); signs come from the view model.
- Rendered equals service: hydrate() on the same scratch DB compared with page text for the hero (net 41,148.30, assets 43,604.04,
  liabilities U+2212 2,455.74, planned +25,866.19, 12 accounts) and every one of the 12 rows (balance, sign, currency, checked, txns,
  subtitle, after planned, credit used %, available and limit; absence of "after planned" where the service has none): 0 mismatches.
  Empty DB: hero 0.00 / 0.00 / 0.00 / 0.00, 0 accounts, matches. Euro Cash prints 1,234.56 EUR and Yen Wallet 50,000 JPY (zero decimals).
- Signs: negatives use U+2212 (6 occurrences), no ASCII hyphen before a digit in main.
- hx-target and duplicate ids after a swap: after the real delete attempt (409, row kept) ids are unique and no horizontal scroll.
  balance-stale has a listener (hero hx-trigger) and emitters in the existing create, edit, delete, reconcile responses.
- Failing saves: see finding 2 (accepted by the brief, UR02b). The new templates contain no forms.

Screenshots viewed (demo and empty, light and dark, in /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR08a/shots, boards in /private/tmp/claude-501/-Users-mikolajkublin-workspace-budget-budget-planner/0eb4ab23-4451-4f62-857f-3e5a0b3150dd/scratchpad/UR08a/design): demo-light-1440-normal, demo-light-375-normal,
demo-dark-1024-normal, empty-light-1440-empty, empty-dark-375-empty, demo-light-1440-row-menu-credit, demo-dark-375-row-menu-credit,
menu-desktop-dark, real-delete, and the matching board images. The other widths and states share the same templates and CSS and had
identical diagnostics (rows.json in the same directory).
