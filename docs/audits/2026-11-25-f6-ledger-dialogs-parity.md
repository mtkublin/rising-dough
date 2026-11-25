# Frontend audit: F6 ledger dialogs handoff parity (T-UR00b)

Date 2026-11-25. Branch wi/ui/sourdough/F6, code audited at b6f6885 (src identical at HEAD 69e65b3; later commits are merges, docs and tests only).
Method: `frontend-visual-audit` skill (Playwright, headless Chromium), scratch DB from `tests/visual/handoff_seed.py` with the `recurring-board` modifier, frozen clock 2026-10-31 (`tests/visual/frozen_server.py`). Never `data/budget.sqlite`.
Screenshots (viewed): scratchpad `shots/<viewport>__<route>.png`, e.g. `1440__txn_edit_invalid_zero.png`, `375__txn_edit_credit_preview.png`, `375__recurring_edit_formula_4.png`, `1440__credit_over_limit.png`.

## Routes
Pages: `/ledger?date_from=2026-10-07&date_to=2026-10-31&page_size=11`, `/ledger?view=planned`, `/ledger?view=recurring`, each with the row menu open (txn-1, planned-p-1, recurring-1).
Dialogs (opened through the row menu / buttons or `htmx.ajax` into `#modal-root`): `/transactions/{1 transit, 5 reconciliation, 11, 30, 28}/edit`, `/planned/1/edit`, `/planned/1/promote`, `/recurring/1/edit` (fixed), `/recurring/4/edit` (formula), `/recurring/1/promote`, `/recurring/1/overrides/new`, `/recurring/5/overrides/new?occurrence_date=2026-10-07&remove=1`, credit-line preview (Credit Card, amount above limit).

## Diagnostics (all rows; 1440 / 1024 / 375)
horizontalScroll=false, duplicateIds=0, consoleErrors=0, requestFailures=0 on every route x viewport (36 page+dialog captures at 1440, 17 at 1024, 17 at 375; 3 x 12 forced-failure and 422 captures excluded from request counts as intentional).
overflowingElements (element wider than viewport, page does not scroll):
- 1024 `/ledger?view=planned` and `?view=recurring`: 10 each: the actions column (`td.rd-row__actions`, right 1058 of 1024) sits inside `div.rd-table-scroll` (`overflow-x:auto`, an intentional table scroller). No CSS changed by F6.
- 375 edit dialogs (txn 1/5/11/30, credit preview, planned edit, recurring fixed/formula): 1-2 each: the last "recent" category chip / hidden input inside `div.rd-catfield__recent` (`overflow-x:auto`, intentional chip scroller). No CSS changed by F6.
All other rows 0. These are raw-diagnostic counts contained by scroll containers; not checked against MAIN (see findings).

## Step 3b
- Swap targets: `#modal-root` matched once before and after every dialog swap; no duplicate ids after swaps.
- Template logic: F6 template diff is `size="plain"` on override-remove and a `hidden` wrapper on credit-line; `rg` for float, `/100`, `*100`, `set` in both: none.
- Rendered numbers equal service values: amount fields show grouped values equal to stored minor units (planned 1 `2,239.80` = 223980; txn 30 `15,800.00` = 1580000; txn 28 `2,155.21` = 215521). Credit line over limit: `87,441.87 over the credit limit (12,557.13 left)` = 99,999.00 - 12,557.13.
- Amount round trip (unchanged re-submit, stored minor units before = after): txn 30, txn 28, planned 1 edit: unchanged. Typed `1,234.50` -> 123450; `1234,50` -> 123450; `1.234,50` and `12 34.50` -> rejected with visible `amount must be a decimal number within range`, stored unchanged; letters are filtered by the field (value unchanged).
- Invalid `0`: visible `Enter an amount above 0.00` under the hero (422).
- Failing saves: forced 404, 409, 500 on txn edit, planned edit and promote, recurring edit and promote, override new: dialog stays open and the toast shows `That item was not found...`, `That item changed in the meantime...`, `Something went wrong on our side...`; none left looking saved.
- Money by currency: all scratch accounts are PLN; no JPY or non-PLN account in the handoff seed, so not exercised.
- Credit-line preview: updates on account/category change using the amount typed before (type amount, then pick account); typing the amount after choosing the account does not refresh the line (trigger is account and category change only), so it showed the stored amount's preview. Not changed by F6; triaged.

## Findings
1. Layout, 375 `/ledger?view=recurring` override list: the month label collides with the amount ("Oct 2026" overdrawn by "15,800.00 PLN", same for Sep, Aug, Jul). Screenshot `375__recurring.png` (crop checked). F6 touched no CSS or that list template; probably pre-existing, not verified on MAIN.
2. overflowingElements at 1024 planned/recurring and 375 edit dialogs: contained by `overflow-x:auto` scrollers (above); non-zero by the skill's rule, no page scroll.
3. Credit-line preview does not refresh on amount edit (above); informational.
