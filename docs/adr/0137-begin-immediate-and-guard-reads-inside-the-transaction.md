# ADR-0137: Write Transactions Begin IMMEDIATE and Guard Reads Live Inside Them

- **Status**: Accepted
- **Date**: 2026-11-21

## Context

Quality audit findings Q-025 (C-09, B-07) and Q-063 (H2-05). `repositories/_shared.transaction` issued a
deferred `BEGIN`. Services read the row that decides a mutation (planned row already promoted? rule
`next_due`? derived balance? last admin?) before opening the transaction, so two requests (double click,
two tabs) both passed the guard and then raced for the write lock. The loser either got `database is locked`
(a 500) on lock upgrade, or both succeeded (two transactions from one planned row; the same recurring
occurrence promoted twice; two reconciliation adjustments). The admin form also treated an absent
`is_admin` field as "uncheck", silently demoting the target.

## Decision

1. `transaction()` opens the outermost transaction with `BEGIN IMMEDIATE`. The write lock is taken up
   front and a competing writer waits on `busy_timeout` (5 s) instead of failing on upgrade. Nested entries
   stay `SAVEPOINT`s. Read-only request paths are unaffected (no transaction opened).
2. Guard reads (existence, state and balance checks that decide whether and how a mutation runs) are made
   inside the same transaction as the writes they guard: `planned.promote_to_actual`,
   `recurring.promote_recurring` and `skip_and_advance`, `reconciliation.reconcile`, and the `users` admin
   services (already inside `_atomically`). A service calling two or more mutators uses one
   `db_transaction` (rule G8).
3. The admin edit path maps a lock wait that exceeds `busy_timeout` to `UserConflict` (the existing 409
   flow), not a 500.
4. `ProfileUpdate.is_admin = None` means unchanged (it already said so; the SQL now honours it). The admin
   edit route passes `None` when the `is_admin` form field is absent. The edit form always sends a hidden
   `is_admin=0` before the checkbox, so an unchecked box still demotes (last value wins).

## Consequences

- A double submit promotes once; the loser re-reads inside the lock and gets `AlreadyPromotedError` (planned),
  promotes the next occurrence (recurring), or `NoAdjustmentNeededError` (reconciliation).
- Writers serialise per database; with one SQLite file and short transactions this is the intended model.
- Long work (bcrypt, network) must stay outside the transaction, as `users.reset_password` already does.

## Alternatives Considered

- **Compare-and-swap on the stamped column only**: fixes promote but not the other guard reads, and still
  fails with `database is locked` under contention.
- **Retry on `OperationalError`**: hides the race instead of serialising it.
