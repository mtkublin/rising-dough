# ADR-0136: Soft-deleted accounts are excluded from balances, stats and converters

- **Status**: Accepted
- **Date**: 2026-11-21
- **Relates to**: [ADR-0130](0130-prevention-regime-and-full-architectural-compliance.md), [ADR-0008](0008-fx-conversion-and-base-currency.md)
- **Finding**: Q-030, Q-015 (OQ-15, answered by the operator 2026-11-21); task T-Q276

## Context

OQ-15 asked which policy applies to archived categories and inactive or deleted rows in each service. Services disagree: some sum the transactions of soft-deleted accounts, some skip them, and converter pickers can offer a deleted account.

## Decision

1. **Soft-deleted accounts are hidden everywhere derived**: net worth and fortune, account balances, statistics and analytics, forecast, and converter or account pickers. Their rows stay in the database (undo and the recently-deleted view keep working) but no derived number includes them.
2. **Archived categories still count.** Archiving a category only hides it from pickers for new entries; historical and current transactions in it remain in budgets, stats and totals.
3. One predicate per read path, applied in the canonical owner (`services/balance.py`, `services/fortune.compute_fortune`, `services/aggregates.py`, the converter account list), not per caller. Every read stays user-scoped.

## Consequences

- Deleting an account lowers net worth immediately; undo restores it. This is the intended, visible effect.
- Tests must pin both halves (deleted account excluded, archived category included) and two-user isolation (T-Q276).

## Alternatives considered

- Include deleted accounts until purged: rejected, a deleted account would keep inflating net worth.
- Treat archived categories like deleted ones: rejected, it would silently rewrite past spending.

## Amendment 2026-11-22 (T-Q276)

Implemented: `TransactionFilter.live_accounts_only` (one SQL predicate, `repositories/transactions._LIVE_ACCOUNT`) is set by the analytics, budget and forecast reads; `services/fx.currency_by_account` is the one converter account map (live accounts only). Balances, fortune and account stats already took the live account list and were correct. Budget spent follows the same rule.

## Amendment 2026-11-22 (T-Q227)

The archived-category half is implemented once in `services/categories.expense_category_ids` / `expense_categories` (archived included) and used by the budget summary, yearly grid, forecast overlay and monthly plan. OQ-7 (three monthly averages stay, documented in `services/aggregates.py`) and OQ-16 (future-dated actuals allowed, one-day sparkline lag accepted) took defaults on 2026-11-21, pending operator confirmation.

## Amendment 2026-11-22 (operator decision; T-Q279, T-Q280)

- **Archived categories reserve no budget (T-Q279).** In the forecast planned-budget overlay, the Budget page, the yearly grid and the monthly plan, an archived category contributes no budget. Transactions already booked in an archived category still count in spent, net worth, analytics and forecast actuals. This supersedes the reading of OQ-15 in the T-Q227 amendment above: "archived included" holds for actuals only; `expense_category_ids` stays the actuals selector and a separate budgeted selector excludes archived categories. The INV-9 test is rewritten to this rule.
- **Planned rows on soft-deleted accounts are hidden (T-Q280).** They are excluded from planned totals and `planned_base_amounts`, consistent with decision 1; undo of the account delete restores them.
- **Effective from the archive month (second round, 2026-11-22).** The archive takes effect from the month the category was archived: past months keep the category's budget; it reserves nothing from that month onward.

Implemented (T-Q279): `services/categories.reserves_budget` is the one predicate (archive month = month of `deleted_at` in the display timezone, ADR-0007); `budget_reserver`, `budgeted_expense_categories` and `budgeted_expense_category_ids` derive from it. `expense_category_ids` stays the actuals selector. `budget_batch.budget_resolver` returns `None` for a non-reserving month, so the forecast overlay and `_planned_budget_per_month` need no per-caller check; `month_summary` and `yearly_grid` use the same predicate. `display_timezone` is threaded from the routers (default `clock.DEFAULT_DISPLAY_TIMEZONE`).

Implemented (T-Q280): `PlannedFilter.live_accounts_only` (one SQL predicate, `repositories/planned._LIVE_ACCOUNT`, mirroring the transactions one) is set by `recurring._planned_items`, so `pending_occurrences` and everything built on it (budget committed-by-window, forecast planned events, upcoming/today, Accounts-tab planned net) skips planned rows of soft-deleted accounts. `linked_occurrence_keys` stays unfiltered so a hidden linked row still suppresses its virtual occurrence. `planned_base_amounts` now uses the live-account currency map. The ledger planned strip total skips rows of deleted accounts; the planned LIST still shows them (unchanged).

## Amendment 2026-11-22 (operator decision, third round)

Promotion of a planned row into an archived category stays refused (T-Q287); no change.
