# ADR-0105: Committed Includes Every Overdue Unpromoted Item

- **Status**: Accepted
- **Date**: 2026-11-16
- **Amends**: [ADR-0039](0039-budget-daily-spend-includes-recurring.md) (lower bound of the committed window)
- **Relates to**: [ADR-0043](0043-forecast-tab-monthly-horizon-and-table.md), [ADR-0085](0085-budget-left-counts-only-budgeted-commitments.md), [ADR-0087](0087-forecast-honours-recurring-next-due.md), [ADR-0089](0089-accounts-planned-net-per-account.md)

## Context

`services.budget.month_summary` computes `committed_minor` (and `unbudgeted_committed_minor`) over `[today, next_income_date)` (ADR-0039). The Plan · Forecast current-period row reuses those totals as its **Expenses** figure (ADR-0043, F5.5). As a result, overdue commitments were silently dropped:

- unpromoted planned expense rows dated before today;
- recurring expense occurrences whose `next_due` is before today (overdue, not yet promoted).

Due-today items were already counted (inclusive lower bound). For budgeted categories the overdue amount re-appeared inside "Planned budget" (it was never subtracted from remaining), so it was mis-attributed; for unbudgeted categories it vanished from the forecast entirely, overstating every EOM balance. The same window also inflated Budget/Today "left" and "left per day".

## Decision

1. The committed window has **no lower bound**: `(-∞, next_income_date)`. Every unpromoted planned expense row dated before `next_income_date` counts, regardless of how old it is; recurring expense occurrences are expanded from `rule.next_due` (unclamped) up to the window end.
2. No period-start clamp. Unpromoted overdue items are by definition still owed; stale or unwanted ones are the user's to delete (planned) or skip (recurring) through the existing flows. The calculation does not try to guess which are redundant.
3. Implementation: `committed_in_window` / `committed_split_in_window` accept `start=None` meaning unbounded; `month_summary` passes `start=None`. Linked-row dedup (ADR-0087), overrides, skips and formula amounts are unchanged.
4. ADR-0085 split is unchanged: budgeted-category overdue items reduce "left"; unbudgeted ones land in `unbudgeted_committed_minor` (informational on Budget, counted in Forecast Expenses).

## Consequences

- Forecast current-period **Expenses** now includes overdue items; EOM balance is lower by the previously-lost unbudgeted overdue amount; budgeted overdue moves from "Planned budget" to "Expenses".
- Budget hero, Today hero and left-per-day drop by the budgeted overdue amount — the cash is still going to leave before payday.
- ADR-0089 (Accounts planned net) still clamps overdue to `>= period_start`; aligning it is a separate decision.
