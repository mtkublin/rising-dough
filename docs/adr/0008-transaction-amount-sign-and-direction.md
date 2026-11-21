# ADR-0008: Transaction Amount Sign & Direction

- **Status**: Accepted
- **Date**: 2026-10-23

## Decision

- `transactions.amount` stored as **positive integer minor units** for direction ∈ `{income, expense, transit}`.
- Direction derived from `categories.direction` enum (`income | expense | transit | adjustment`).
- **Exception**: direction `adjustment` allows a **signed** amount (positive for inflow, negative for outflow). This encodes the sign of a reconciliation delta without needing two categories.

## Validation rules

- `amount != 0`.
- `direction ∈ {income, expense, transit}` → `amount > 0`.
- `direction == adjustment` → sign is free.

## Balance derivation sign rules

- `income` → `+amount` on `account_id`.
- `expense` → `-amount` on `account_id`.
- `transit` → `-amount` on `account_id`, `+amount` on `dest_account_id`.
- `adjustment` → `+amount` on `account_id` (amount already signed).

## Consequences

- Direction has a single source of truth (the category) for the normal path.
- Reconciliation uses one seeded "Reconciliation" category instead of two (Reconciliation+ / Reconciliation-).
- Balance derivation has a tiny per-direction switch; still a pure function.
- Transits are naturally excluded from income/expense aggregates by filtering direction.

## Alternatives Considered

- **Signed amount always**: flexible; opens door to "positive expense" / "negative income" bugs.
- **Two reconciliation categories**: cleaner model purity; worse UX (user must pick direction manually).
- **Separate `inflows` / `outflows` tables**: DRY violation and join-heavy unified log view.

## Amendment 2026-11-21 (T-Q210, Q-004): transit shape is validated on every write path

A `transit` row without a destination makes `derive_balance` raise, so /accounts, /today and /forecast return 500 until the row is deleted. One rule now guards every write path:

`services/transactions.validate_transit_shape(direction, account, dest)` (pure; raises `ValidationError`):

- `direction == transit` requires a destination account that exists for the same user, has the same currency as the source (ADR-0006, no cross-currency transit in v1) and differs from the source.
- Other directions are unconstrained (a stored destination on a non-transit row is ignored by balance derivation).

It is applied by create and update of transactions, create and update of planned transactions, promotion (planned and recurring, via `_promotion.validate_promotion`) and reconcile (a transit category chosen for a reconciliation has no destination and is rejected). Routers map `ValidationError` to HTTP 422 with a visible form error; a 500 is never the outcome of invalid input.

OQ-9 default taken 2026-11-21, pending operator confirmation: user-defined transit categories stay allowed; the shape rule above is what makes them safe.
