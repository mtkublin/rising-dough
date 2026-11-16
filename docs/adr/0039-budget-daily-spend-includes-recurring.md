# ADR-0039: Budget "Left to Spend per Day" Includes Recurring Commitments

- **Status**: Accepted (amended by [ADR-0085](0085-budget-left-counts-only-budgeted-commitments.md): only budgeted categories' commitments reduce left)
- **Date**: 2026-10-27
- **Amends**: ADR-0025 §F4.6, ADR-0038

## Context

F4.6 defines the budget headline metric:

```
left_daily_spend = remaining_minor ÷ days_until_next_income
```

where `remaining_minor` is the sum of `(budget_resolved − spent)` per expense category for the current month, and `days_until_next_income` comes from the income anchor (ADR-0025).

In practice the metric overstates what the user can safely spend: recurring expenses that are *scheduled but not yet promoted* (rent, utilities, subscriptions) are already committed money. The numerator should pre-subtract them so a user who sees "120 PLN / day" does not then watch their rent transfer wipe the budget two days later.

## Decision

Extend `MonthSummary.remaining_minor` to be split into:

```python
@dataclass(frozen=True, slots=True)
class MonthTotals:
    budgeted_minor: int
    spent_minor: int           # actuals in month-to-date
    committed_minor: int       # NEW — recurring + planned not yet promoted,
                               # window = [today, next_income_date)
    remaining_minor: int       # budgeted − spent − committed
```

- `committed_minor` sums, over all **live expense-direction** rules + planned rows:
  - `recurring_rules.next_due ∈ [today, next_income_date)` (apply override on that date if present; drop `state=skipped`).
  - `planned_transactions.operation_date ∈ [today, next_income_date) AND promoted_to_txn_id IS NULL AND category.direction = 'expense'`.
- `left_daily_spend_minor = remaining_minor ÷ days_until_next_income`, same banker's-rounding rule.
- `committed_minor` renders as a dim sub-line on both the Budget hero and the Overview Month panel: `"X committed (recurring + planned)"`. The number is informational — it keeps the subtraction visible instead of silent.

### Window boundaries

- Lower bound is **inclusive today** (recurring due today still counts, since promotion is manual).
- Upper bound is **exclusive next-income-date** (the income arrival resets the budget cycle in the user's mental model).
- When the anchor is unset or stale, the fallback window is `[today, end_of_month)` per F4.6.

### Service shape

New pure helper on `services.budget`:

```python
def committed_in_window(
    conn: sqlite3.Connection,
    start: date,
    end: date,
) -> int:
    """Sum of future recurring + unpromoted planned expense amounts
    whose effective date falls in [start, end). Overrides applied;
    skipped occurrences excluded. Transit direction excluded.
    """
```

- Composes `recurring_repo.list_rules(active_only=True)` + `recurring_repo.list_overrides` + `planned_repo.list_filtered(promoted=False)`.
- Reuses `services.recurring.expand` to enumerate due dates for each rule within the window (same generator forecast already uses, F5.2) — this is the one surviving caller of `expand` on the Budget side.
- Direction derived from `categories_repo.find_by_id`; non-expense (income, transit, adjustment) excluded.

## Consequences

- The "Left per day" number is honest. Over-commitment surfaces earlier.
- `committed_minor` is deterministic given a fixed DB snapshot — testable without time mocking (inject `today`, same pattern as ADR-0007).
- If the user promotes a recurring row, `committed_minor` drops and `spent_minor` rises on the next request — net effect on `remaining_minor` is zero. Chart stays stable across the promote click.
- The forecast service (F5.2) is unchanged — it already projects recurring occurrences via `expand`. ADR-0038's `next_due` persistence does not conflict: forecast queries both the current `next_due` and the generator for the horizon beyond.
- Backwards-compatible template: existing `summary.remaining_minor` continues to render but is now the post-commit value; the Budget / Overview partials add one new line for `summary.totals.committed_minor` beneath the headline.

## Alternatives Considered

- **Separate "safe-to-spend" metric alongside existing remaining.** Rejected — doubles the UI real estate and asks the user to pick which number to trust. The user's question is one: "what can I spend today without overdrawing myself before payday?"
- **Pre-materialise upcoming recurring into `transactions` at the start of each day.** Rejected — reintroduces the scheduler we deliberately avoided (ADR-0012, ADR-0038).
- **Include *all* planned/recurring regardless of window.** Rejected — pre-paying rent twelve months out should not zero today's daily spend.
