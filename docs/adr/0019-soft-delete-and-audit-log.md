# ADR-0019: Soft Delete + Polymorphic Audit Log

- **Status**: Accepted
- **Date**: 2026-10-23

## Decision

### Soft delete

Every mutable table has a nullable `deleted_at` timestamp. Repository helpers filter `WHERE deleted_at IS NULL` by default and accept an `include_deleted: bool = False` kwarg for admin paths. "Deleting" an entity sets `deleted_at = now()`.

Hard delete is only available via a maintenance script, not through the UI.

### Audit log

A single shared polymorphic table captures every mutation:

```
audit_log(
  id,
  entity_type,      -- 'transaction' | 'planned_transaction' | 'recurring_rule' | ...
  entity_id,
  changed_at,
  operation,        -- 'create' | 'update' | 'delete' | 'undelete'
  prev_json,        -- NULL on create
  new_json          -- NULL on delete
)
```

Every repository mutation calls `write_audit(...)` in the same DB transaction via a shared helper. Pure, DRY, testable.

## Consequences

- Full timeline recoverable: "what did I change on 2026-10-10?"
- Undo-delete is cheap (clear `deleted_at`).
- Analytics on historical data unaffected provided queries respect `deleted_at IS NULL`.
- A future "revert this edit" feature is possible without new schema.

## Alternatives Considered

- **Hard delete, no history**: lossy; user mistakes are unrecoverable.
- **Per-entity history tables**: more tables, same effect; higher maintenance.
- **SQL triggers**: DB-coupled, harder to test, harder to port.
- **Per-field history columns**: schema bloat and fragile.

## Amendments

- 2026-11-21 ([ADR-0137](0137-begin-immediate-and-guard-reads-inside-the-transaction.md)): the shared transaction helper opens `BEGIN IMMEDIATE`, and the guard reads that decide a mutation run inside the same transaction as the mutation and its audit rows.
- 2026-11-21 (T-Q228, Q-024, Q-049; OQ-10 and OQ-11 default taken 2026-11-21, pending operator confirmation): **undo is an audited action.** A batch undo never erases or rewrites the trail: it writes its own `audit_log` rows (prev = state before the undo, new = restored state) through the audited repository helpers, inside one `db_transaction` (ADR-0137). Undo targets the specific batch, never "the latest audit row of the entity": the planned undo clears `promoted_to_txn_id` by compare-and-set only where it still equals a transaction id of the batch; the recurring undo carries the id of the audit row each advance wrote, restores that row's `prev_json` only while it is still the newest audit row of the rule (the rule is unchanged since), and skips, reporting it, any rule edited meanwhile. `user_preferences` writes are audited (`entity_type = 'user_preference'`) through `mutate`. Domain audit rows record `user_id` (+ actor) as ADR-0122 states; NULL `ip`/`session_id`/`user_agent` on domain rows is intended and needs no schema change (those columns belong to auth events).
- 2026-11-21 (T-Q230, Q-026; operator question deferred, safer default taken, pending operator confirmation): **an account is archived only when nothing still depends on it.** `services/accounts.archive_account` runs inside one `db_transaction` (ADR-0137) and refuses with `ConflictError` (409, existing error partial/toast path) when the account has a non-zero balance (via `services/balance.derive_balance`), live active recurring rules (as source or destination) or unpromoted live planned rows. The message names every blocker ("Cannot archive account: Balance is not zero; 2 recurring rules use this account; 1 planned transaction uses this account"). No silent cascade; nothing is written, no audit row, on refusal. `ConflictError` becomes a plain exception (a frozen dataclass exception cannot propagate).
- 2026-11-21 (T-Q268, Q-025, B-14): **read-filter classification.** Fixed (predicate added, tests): `budgets.set_default/set_recurring/set_one_off` re-reads, `recurring.list_overrides/upsert_override/delete_override` (parent rule must be live), `snapshots.list_for_account/create` (account must be live), `audit.list_entries` (takes `user_id`; `None` = ownerless system rows) and `audit.recent` (explicit keyword `user_id`; `None` is the cross-user debug tail, whose service masks other users' payloads). Intentionally unfiltered, made explicit with a named `include_deleted` keyword (default keeps the old behaviour): `_shared.require_owned` (soft-deleted parents count as owned, liveness is the service's concern), `users.owns_accounts` (live or not), `webauthn._get_by_id` (revoke reads the tombstone to report "already revoked"). Secret-keyed lookups with no user id known: `sessions.touch_session`, `sessions.rotate_session_token` (key is the hash of the bearer token) and `webauthn.get_by_credential_id` (login lookup by authenticator credential id) are permanent entries (ADR-0130 amendment 2026-11-21, T-Q268).
