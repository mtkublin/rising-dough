# T-D60 — IP / user-agent retention purge (90 days)

- **Phase**: 5 — Data-protection quick wins
- **Parallel-safe**: yes
- **Depends on**: T-D14, T-D19a
- **References**: [ADR-0078](../../../adr/0078-v3-data-protection-quick-wins.md) §7

## Context

`audit_log.ip`, `audit_log.user_agent`, and `sessions` rows are kept forever. They are personal data with no purpose after ~90 days.

## Deliverables

1. `services/retention.py` (pure functions + one `purge(conn, now, settings)` entry): null `audit_log.ip`, `audit_log.user_agent` where `changed_at < now - retention_personal_days`; delete `sessions` rows with `revoked_at` or `expires_at` older than the same bound. Setting `retention_personal_days` (default 90, validator 7..3650).
2. `python -m budget_planner.db.retention` CLI; container entrypoint runs it after `startup_migrate` (non-fatal on error: log + continue).
3. App lifespan: run `purge` once per 24 h on the FastAPI lifespan task (cancel-safe on shutdown, T-D15).
4. Logs `event="retention_purge"` with counts only.

## Acceptance criteria

- Unit: boundary cases (exactly 90 d, 89 d, 91 d); idempotent; live sessions untouched.
- Integration: entrypoint run on a scratch DB purges seeded old rows.

## Validation hook

```sh
just test tests/unit/services/test_retention.py
```
