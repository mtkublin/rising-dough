# ADR-0089: Accounts Tab Shows Planned Net per Account and Projected End-of-Period Balance

- **Status**: Accepted
- **Date**: 2026-11-06
- **Relates to**: [ADR-0085](0085-budget-left-counts-only-budgeted-commitments.md), [ADR-0087](0087-forecast-honours-recurring-next-due.md), [ADR-0041](0041-budget-period-anchor-window.md), [ADR-0024](0024-liability-accounts-and-credit-limit.md)

## Context

The Accounts tab shows only the current derived balance. The user wants to see, per account, how much money is still going to leave or arrive before the next paycheck, and where the balance ends up.

## Decision

New service `services/account_planned.py` computes, per account and in the account's own currency, the **signed net of planned (not-yet-paid) payments** in the current fiscal period, plus a projected end-of-period balance `balance + net`.

1. **Window** `[period_start, period_end)`.
   - `period_start` = same resolution as budget (`_resolve_period_start`, ADR-0041): last landed anchor-category income `<= today`, else the 1st of the current month.
   - `period_end` = next income-anchor date (`income.next_anchor_date(after=today)`); falls back to end-of-month **only** when there is no anchor category or no next income hit. The budget shortcut "`budgeted_total == 0` -> end-of-month" is deliberately **not** replicated: the user rejected it for this feature.
2. **Items**: unpromoted planned rows dated in the window, **including overdue** ones (dated before today but `>= period_start`, still unpromoted); plus recurring occurrences in the window that are not yet promoted, expanded from `max(rule.next_due, period_start)` by **canonical** occurrence date (ADR-0087 rule, generalised into `recurring.expand_unpromoted`). Early-promoted occurrences are never counted; overdue unpromoted ones are. Formula amounts, amount overrides and skips are honoured via `rt_expand`.
3. **Directions**: net of **all** categories, budgeted and unbudgeted alike (unlike ADR-0085 "left", which counts only budgeted ones): expense `-amount` on `account_id`; income `+amount` on `account_id`; transit `-amount` on source and `+amount` on `dest_account_id`. Adjustment-direction rows are ignored.
4. **UI**: a sub-line under Balance, no new column: `-9,824.01 planned -> 2,575.99` (outflow uses the `neg` token, inflow `+700.00` the `pos` token). Hidden entirely when net is 0. Liability accounts show the same sub-line; the credit "Available" bar is unchanged. Rendered in the index row and in the `_row.html` partial (reconcile swap). The hero gains a "Planned" figure = sum of per-account net for accounts in `settings.base_currency` only (same rule as `compute_fortune`; no FX).
5. Router stays thin; the service does the math with frozen dataclasses and repositories own SQL.

## Consequences

- `forecast._expand_unpromoted` becomes a thin caller of the shared `recurring.expand_unpromoted` (no behaviour change).
- `services/budget.py` is untouched; period resolution is reused through a new public wrapper (`resolve_period_start`).
- Foreign-currency accounts show their own net; the hero ignores them (consistent with the Assets/Liabilities hero).
