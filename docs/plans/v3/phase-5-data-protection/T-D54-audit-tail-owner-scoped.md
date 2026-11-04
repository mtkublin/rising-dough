# T-D54 — Audit tail is owner-scoped

- **Phase**: 5 — Data-protection quick wins
- **Parallel-safe**: yes
- **Depends on**: T-D43
- **References**: [ADR-0078](../../../adr/0078-v3-data-protection-quick-wins.md) §1, [ADR-0061](../../../adr/0061-v3-multi-user-admin-bootstrap-and-data-isolation.md) §1

## Context

`GET /debug/audit-tail` (admin-only) returns the newest audit rows of **every** user with `prev`/`new` payloads — amounts, descriptions, names. That is the one confirmed violation of ADR-0061 ("the admin cannot read non-admin users' … data").

## Deliverables

1. `repositories/audit.py::recent` also selects `user_id` and `actor_user_id`; `AuditEntry` gains both (nullable).
2. `services/audit_tail.py::audit_tail(conn, viewer_user_id, n)` — payloads (`prev`, `new`) returned only when `entry.user_id == viewer_user_id` or (`entry.user_id is None` and `entry.actor_user_id == viewer_user_id`); otherwise both are the constant `OTHER_USER = "[other-user]"`. Each entry also exposes `user_id`.
3. `web/routers/debug.py` passes the admin's id.
4. `tests/smoke/test_prod_smoke.py` (T-D43): the audit assertion for the second user's transaction checks presence + metadata only; add an assertion that its `new` is `"[other-user]"`.

## Acceptance criteria

- Unit: own rows show payloads; other users' rows show `"[other-user]"`; secret-key scrubbing unchanged.
- Integration: two users; user B creates a transaction; admin A's `/debug/audit-tail` contains the row with `entity_type='transactions'`, `user_id=B`, `new == "[other-user]"`.
- No other caller of `audit_tail` left un-updated (`mypy --strict`).

## Validation hook

```sh
just test tests/unit/services/test_audit_tail.py tests/integration/web/test_debug_audit_tail.py
```
