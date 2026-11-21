# Frontend audit: T-Q209 ledger planned strip and recurring summary

Change: T-Q209 (Q-010 sign part, ADR-0008). `templates/ledger/index.html` prints
`recurring_summary.*_display` and `planned_summary.net_display` (service-formatted via
`domain.money.format_money`) instead of `/ 100.0` and a hard-coded `PLN`.

Run: `frontend-visual-audit` (Playwright, headless Chromium), app on a migrated scratch copy of
`data/demo.sqlite` at `/tmp/t-q209.sqlite` (never `data/budget.sqlite`), logged in through the password form.

## Routes and diagnostics

| Route | Viewport | horizontalScroll | overflowingElements | duplicateIds | consoleErrors | requestFailures |
|---|---|---|---|---|---|---|
| /ledger?view=actual | 1440 | false | 0 | 0 | 0 | 0 |
| /ledger?view=planned | 1440 | false | 0 | 0 | 0 | 0 |
| /ledger?view=recurring | 1440 | false | 0 | 0 | 0 | 0 |
| /ledger?view=actual | 1024 | false | 0 | 0 | 0 | 0 |
| /ledger?view=planned | 1024 | false | 0 | 0 | 0 | 0 |
| /ledger?view=recurring | 1024 | false | 10 (table.ledger descendants) | 0 | 0 | 0 |
| /ledger?view=actual | 375 | false | 10 (table.ledger descendants) | 0 | 0 | 0 |
| /ledger?view=planned | 375 | false | 10 (table.ledger descendants) | 0 | 0 | 0 |
| /ledger?view=recurring | 375 | false | 10 (table.ledger descendants) | 0 | 0 | 0 |

Triage: the `overflowingElements` entries are the ledger table wider than the narrow viewport inside
its horizontally scrollable wrapper; `horizontalScroll` stays false. The table markup is untouched by
this change and the same entries appear on the untouched Actual view at 375 (pre-existing, out of scope).

## Screenshots (viewed)

`/tmp/fe-audit-tq209/{desktop,tablet,mobile}___ledger_view_{actual,planned,recurring}.png`.
Checked: desktop Planned strip reads "1 items · -2,239.80 PLN" (one pending Car expense of 2,239.80, now
signed negative); mobile Recurring strip shows "13,754.94 PLN" out and "23,252.61 PLN" in, the second wraps
its currency onto a second line but nothing is clipped.

## Step 3b

1. Swap targets: the `#ledger-table` hx-target/hx-swap lines are untouched by the diff.
2. Failing saves: no state-changing form touched; N/A.
3. No arithmetic in templates: the strip block has no `/ 100`, `float` or hard-coded currency left.
4. Money formatting: strips use `format_money`; they sum in the base currency without per-row FX (EUR rules
   are added unconverted in the demo data), which is the T-Q215/T-Q216 scope. No JPY check in this task.
5. Rendered equals service: planned strip -2,239.80 PLN equals the single pending row's signed amount; exact
   values asserted in `tests/unit/services/test_ledger_planned_totals.py` and
   `tests/integration/web/test_ledger_strips_signed.py` (income 5,000.00 and expense 1,200.50 give 3,799.50 net).
6. Duplicate ids: 0 on every route and viewport; no new HX-Trigger events.
7. Scratch data only: yes.
