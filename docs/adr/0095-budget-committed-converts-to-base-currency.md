# ADR-0095: Budget `committed` Converts to Base Currency

- **Status**: Accepted
- **Date**: 2026-11-06
- **Amends**: ADR-0085 (committed figures are base-currency), ADR-0039
- **Relates to**: ADR-0006 (account owns currency; aggregates convert to `base_currency`), ADR-0042, ADR-0043

## Context

`services.budget._committed_by_category` summed unpromoted planned rows and recurring occurrences as raw minor units regardless of the owning account's currency. A planned 120.00 EUR expense counted as 120.00 PLN in `committed_minor`, `unbudgeted_committed_minor`, `remaining_minor`, `left_daily_spend_minor` and (ADR-0085 §5) the Forecast fiscal-row Expenses. The Forecast budget overlay (`_committed_future_for_category`, F5.2) had the same raw sum against a base-currency budget.

## Decision

1. Every planned row / recurring occurrence amount is converted to `base_currency` (settings, default PLN) using the **account's** currency before being summed. Base-currency accounts are untouched.
2. Items are future-dated, so the rate is the **latest cached rate on or before today** (exact-today hit preferred), never the item's own date. Implemented with `fx.convert_cached`: cache only, no network on page render.
3. **Missing rate**: degrade to the native amount (rate 1) and log a warning, identical to the Today account rows (`today_data.collect_account_rows`). A render must not fail.
4. The same helper (`budget.base_amount_converter`) is used by `forecast._committed_future_for_category`, so the overlay and the fiscal row agree.
5. `services/account_planned.py` is unchanged: per-account figures stay in account currency; its hero sums base-currency accounts only.

### Amendment (T-FIX6): `spent` converts too, at the historical rate

6. Per-category posted `spent_minor` (and the analytics derived from the same transaction lists: delta vs previous month, this-year / overall averages, month totals spent, `remaining_minor`, `left_daily_spend_minor`, Today hero spent/left, Forecast figures consuming them) converts to `base_currency`.
7. Unlike `committed` (future-dated, rate at today), posted transactions follow ADR-0006: each converts at the latest cached rate on or before **its own `operation_date`** (`budget.base_txn_converter`, using `fx.convert_cached`; no network).
8. Missing rate: native amount plus a logged warning (same fallback as §3). Base-currency accounts short-circuit with no lookup. Existing exclusions (expense direction only; transfers/adjustments out) are unchanged.

## Consequences

- `committed`, its budgeted/unbudgeted split, `remaining`, `left_daily_spend` and Forecast fiscal Expenses are in base currency.
- Without a cached rate a foreign-currency item is over/under-stated by the rate (visible in logs), not hidden.
