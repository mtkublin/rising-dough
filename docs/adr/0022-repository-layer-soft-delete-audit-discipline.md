# ADR-0022 — Repository Layer: Soft-Delete + Audit Discipline

**Status**: accepted (2026-10-23)

**Amended by**: [ADR-0130](0130-prevention-regime-and-full-architectural-compliance.md) (2026-11-20: the deferred static-analysis rule for SQL outside repositories is now a guard)

**Context**

`docs/tasks.md` references **ADR-0022** from T-013 and T-028, but the ADR
index topped out at ADR-0021 (recorded gap in the T-013 plan under
`docs/plans/phase-1/T-013-repository-layer.md`). This ADR closes that gap
and pins the invariants that every repository function in
`src/budget_planner/repositories/` must satisfy.

The repository layer is the only path between services and SQL. ADR-0019
established that every mutable table has a `deleted_at` column and that
every mutation emits an `audit_log` row. This ADR specifies **how** that
discipline is enforced in Python.

**Decision**

1. **One module per entity** under `src/budget_planner/repositories/`, each a
   collection of pure functions (ADR-0021). No classes beyond frozen
   dataclasses defined in `src/budget_planner/domain/`.

2. **Shared mutator** (`repositories/_shared.mutate`) is the only path to
   `INSERT` / `UPDATE` statements that touch soft-delete-aware tables. It
   wraps the action in an explicit `BEGIN` / `COMMIT`, writes an
   `audit_log` row with the previous and new serialised entity in the same
   transaction, and rolls back on any exception. Any mutation that bypasses
   `mutate(...)` is a lint-level violation.

3. **Soft-delete filter is default-on.** Every reader (`find_by_id`,
   `find_by_name`, `list_all`, `list_filtered`) appends
   `AND deleted_at IS NULL` unless the caller passes
   `include_deleted: bool = False` (admin-only paths).

4. **`updated_at` is explicitly bumped** by every UPDATE statement (SQLite
   does not auto-bump). `deleted_at` and `updated_at` are set in the same
   UPDATE for `soft_delete`. `undelete` sets `deleted_at = NULL` and bumps
   `updated_at` similarly.

5. **Audit JSON** uses `json.dumps(..., default=str, sort_keys=True)`. The
   `prev_json` field is `NULL` on `create`; `new_json` is `NULL` on
   `delete`. `undelete` records the restored row as `new_json` and the
   soft-deleted row as `prev_json`.

6. **Append-only entities** (`account_snapshots`, `fx_rates`, `audit_log`)
   bypass soft-delete; their repositories do not expose
   `soft_delete`/`undelete`. They still write to `audit_log` on insert
   except `audit_log` itself (which is the ledger).

7. **Error handling**: repositories raise `LookupError` for unknown ids on
   `update`/`undelete`. SQLite `IntegrityError` is NOT translated — services
   decide how to surface it (validation errors, 400 responses, etc.).

8. **Transactions**: `_shared.transaction(conn)` is the only approved
   context manager for explicit BEGIN/COMMIT. Repositories must never call
   `conn.commit()` or `conn.rollback()` directly.

**Consequences**

- Services become straightforward: they compose repository calls and reason
  about domain shapes without owning the audit discipline.
- Tests can assert the audit row exists in the same transaction without
  mocking.
- Future enforcement option: a static-analysis rule (`ast` grep) that
  rejects raw `UPDATE` / `INSERT` strings outside `_shared.mutate`.
- Future multi-user auth (not planned for v2 or v3) will need to extend `mutate(...)` with a
  `user_id`-aware audit author field; we accept this debt knowingly.

## Amendments

- 2026-11-21 (T-Q228, Q-024, Q-049): the three audit-free helpers (`set_next_due`, `set_inactive`, `mark_override_promoted`, plus `restore_rule_progress`) live in `repositories/_unaudited.py`, imported only by `services/recurring.py`, which writes the paired audit row in the same transaction (`tests/architecture/test_unaudited_imports.py`). Routers hold no SQL for undo; `services/planned.undo_batch` and `services/recurring.undo_batch` own it. `repositories/audit.py` reads are `user_id`-scoped. See ADR-0019 amendment of the same date.
