# Frontend audit: T-Q216 one money renderer

Change: T-Q216 (Q-011, Q-029, ADR-0006 amendment 2026-11-21). Every `/ 100.0` and two-decimal
`"{:,.2f}".format(...)` in templates, charts and routers is replaced by the `money_num(ccy)`,
`money_whole(ccy)`, `money_major(ccy)`, `bps_percent` filters or `domain.money` helpers
(`minor_to_major`, `major_float`, `percent_of`, `bps_to_percent`). Per-day figures come from
`services.today.daily_share_minor` (router-supplied), not template arithmetic. The exponent table is
complete (ISK, CLP, UGX and 13 other 0-decimal codes; 7 three-decimal codes).

Run: `frontend-visual-audit` (Playwright, headless Chromium), app on a migrated scratch copy of
`data/demo.sqlite` at `/tmp/t-q216.sqlite` (never `data/budget.sqlite`), plus one JPY account
("Tokyo JPY", 12,345) and a JPY->PLN rate, logged in through a minted session.

## Routes and diagnostics

Routes: `/today`, `/plan?tab=budget|year|forecast|analytics`, `/accounts`, `/ledger?view=actual`,
`/ledger?view=recurring`, `/forecast`; each at 1440, 1024 and 375.

| Diagnostic | Result (27 route x viewport runs) |
|---|---|
| horizontalScroll | false everywhere |
| duplicateIds | 0 everywhere |
| consoleErrors | 0 everywhere (after adding the JPY rate; see note) |
| requestFailures | 0 everywhere |
| overflowingElements | 0 at 1440; table descendants inside `.rd-table-scroll` wrappers at 1024 (`/ledger?view=recurring`) and 375 (`/plan?tab=budget|analytics|forecast`, `/forecast`, `/ledger`); page-level `horizontalScroll` stays false |

Note: the first run returned 500 on the forecast routes because the scratch DB had a JPY account without an
FX rate (`FxUnavailableError`, T-Q212 / INV-10, not part of this change); adding a rate row fixed it.

## Step 3b

1. Swap targets: no `hx-target`/`hx-swap` line touched.
2. Failing saves: no state-changing form changed; `/today/afford?amount=1.234` returns 422 (more decimals than PLN allows).
3. No arithmetic on money in the touched templates: no `/ 100`, `* 100`, `float` or `"{:,.2f}"` remains in templates
   (two percent-of-total lines, `_card.html` and the heatmap weight, are not money scale and stay with T-Q237).
4. Rendered equals service: `/today` hero -17.00 PLN/day = -1,801.72 left / 106 days; Spent 5,014.55 and Committed
   3,236.25 equal the summary totals; Plan budget bar -17.00 PLN/day and 3,236.25 committed agree with /today;
   `/accounts` shows "Tokyo JPY 12,345 JPY" (not 123.45); forecast NOW -18,509 PLN whole units;
   ledger day nets "net -35.50".
5. Exact values asserted in `tests/unit/domain/test_money_exponents.py` and INV-6a/6b
   (`tests/integration/invariants/test_inv_06_currency_exponent.py`, `/today` JPY balance renders `12,345`).
6. Scratch data only: yes.
