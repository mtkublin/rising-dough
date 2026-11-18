# ADR-0122: Domain Audit Rows Record Owner and Actor

- **Status**: Accepted
- **Date**: 2026-11-18
- **Amends**: ADR-0019 (audit log), ADR-0022 (`mutate` contract), ADR-0061 §audit, ADR-0073 §5
- **Relates to**: ADR-0078 §1 (audit tail owner scope)
- **Task**: T-D145

## Context

ADR-0061 requires every mutation to record the acting `user_id`; ADR-0073 added `actor_user_id` for admin actions on other users' rows. Only the `users` repository and the auth services ever did this, because they receive a `RequestCtx` from their routers. Every other domain write goes `router -> service -> repository -> _shared.mutate`, and none of those layers passed a `RequestCtx`. `mutate` therefore fell back to `RequestCtx.empty()` and wrote `user_id` and `actor_user_id` as NULL (introduced by T-D14, migration 0013 and the `request_ctx` default, "so existing call sites keep working").

The drill run 44356288331 showed it: a non-admin's account, category and transaction rows had both columns NULL. `audit_tail` (ADR-0078 §1) treats a row with no owner as `[other-user]`, so users could not see their own history.

## Decision

1. `_shared.mutate` and `services.audit.write_audit` take a **mandatory** keyword `user_id: int | None`: the owner of the mutated row. A caller can no longer forget it; `None` is an explicit statement that the entity has no owner (only `fx_rate`, a global table).
2. The row is written with `user_id = owner` and `actor_user_id = owner`. Domain repositories are scoped by `user_id` (ADR-0061 §5), so every domain write is a self-service write; no admin acts on another user's domain rows. Admin actions on `users` rows keep the ADR-0073 contract (`user_id` = admin, `actor_user_id` = admin, `entity_id` = target).
3. The owner is taken from the repository's own `user_id` argument, not from `RequestCtx`. The `RequestCtx` columns `ip`, `session_id` and `user_agent` of domain rows are still NULL; plumbing `RequestCtx` through every router and service is a separate, larger change (follow-up, not part of T-D145).
4. Migration `0016_audit_backfill_owner.sql` fills `user_id` on existing rows from the owning entity row. `actor_user_id` stays NULL on old rows (not recoverable); `audit_tail` ownership uses `user_id` first, so that is harmless.

## Consequences

- Both columns are filled for all domain writes, and `audit_tail` shows users their own payloads.
- New repositories using `mutate` must pass `user_id=`; mypy and the test suite fail otherwise.
- If an admin ever mutates another user's domain rows, `actor_user_id` must be passed separately (new keyword); not needed today.
- Tests: `tests/integration/test_audit_attribution.py`, `tests/integration/web/test_audit_attribution_web.py`.
