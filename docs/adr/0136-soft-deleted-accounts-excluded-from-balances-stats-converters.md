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

## Amendment 2026-11-22 (T-Q227)

The archived-category half is implemented once in `services/categories.expense_category_ids` / `expense_categories` (archived included) and used by the budget summary, yearly grid, forecast overlay and monthly plan. OQ-7 (three monthly averages stay, documented in `services/aggregates.py`) and OQ-16 (future-dated actuals allowed, one-day sparkline lag accepted) took defaults on 2026-11-21, pending operator confirmation.
