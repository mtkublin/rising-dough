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
