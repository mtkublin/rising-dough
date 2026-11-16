# ADR-0085: Budget "Left" Counts Only Commitments in Budgeted Categories

- **Status**: Accepted
- **Date**: 2026-11-06
- **Amends**: ADR-0039, ADR-0041 (`left_daily_spend` numerator)
- **Amended by**: ADR-0095 (committed figures convert to base currency)

## Context

ADR-0039 defines `remaining_minor = Σ(budgeted − spent over budgeted categories) − committed`, where `committed` was the sum of **every** unpromoted planned expense and active recurring expense occurrence in `[today, next_income_date)`, regardless of whether the row's category has a budget.

Bug (2026-11-06): promoting the income-anchor planned payment one day early moved `next_income_date` from "tomorrow" to about a month away. The window then swallowed a month of mostly unbudgeted bills (rent, subscriptions, insurance) and "left" showed -9,824.01 PLN while every budgeted category showed 0 spent.

The ADR-0039 claim "promotion is net-zero on remaining" only holds for budgeted categories: a planned row reduces left, while its promoted actual in an unbudgeted category does not (those are excluded from `spent_total`). So promoting an unbudgeted bill *raised* left, and shifting the window changed left by amounts the budget never covered.

## Decision

1. `committed_minor` (the figure subtracted from remaining, shown in the "committed" sub-line, and used for `left_daily_spend`) counts only planned + recurring expense occurrences whose category has a **resolved budget** for the month (same `resolve_budget` used by the per-category table; budget `None` means unbudgeted). A budget of 0 is a budget.
2. A separate `MonthTotals.unbudgeted_committed_minor` carries the same window sum for expense categories **without** a budget. It is informational only: rendered as a sub-line next to the committed line on /budget and Plan · Budget ("+ X planned in unbudgeted categories (not counted)"). It never affects `remaining_minor` or `left_daily_spend_minor`.
3. Promotion is net-zero on `remaining_minor` for both kinds: budgeted planned moves from committed into spent; unbudgeted planned moves from the informational line into an actual that is also ignored by left.
4. Zero-budget months keep both committed figures at 0 (no window math; ADR-0039).
5. Forecast (F5.5) current-fiscal-row `Expenses` = `committed_minor + unbudgeted_committed_minor` (cash-flow reality: unbudgeted bills still leave the account), `Planned budget` stays `max(remaining_minor, 0)`. Month picker overrides (Plan, non-current month) zero both committed figures.

No schema change. `committed_in_window` keeps its total-of-all-expenses contract; a new `committed_split_in_window` returns `(budgeted, unbudgeted)`.

## Consequences

- Left no longer swings by unbudgeted bills when the income-anchor window moves.
- Users who want an unbudgeted bill to reduce left must give its category a budget.
- Recurring expansion verified: occurrences are anchor-based on `rule.start_date`, so clamping the generator window to `max(next_due, today)` does not double count (regression test added).
