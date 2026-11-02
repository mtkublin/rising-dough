# T-D04 — Litestream-friendly database path

- **Phase**: 1 — App Prerequisites
- **Parallel-safe**: yes
- **Depends on**: T-D03 (reads `env`)
- **Blocks**: T-D23 (cloud-init renders `/data/budget.db`)
- **References**: ADR-0034 §2

## Context

ADR-0034 fixes `/data/budget.db` as the production path (host-mounted volume shared with the Litestream sidecar). Dev stays on `data/budget.sqlite` so the existing `just dev` loop continues to work with no env file. Switching defaults by `env` keeps dev ergonomic without leaking production paths into local work.

ADR-0034 §2 also requires `PRAGMA wal_autocheckpoint = 0;`. Phase 1 adds a startup assertion that production misconfigurations fail fast rather than silently discarding WAL frames Litestream has not yet shipped.

## Deliverables

1. `src/budget_planner/config.py`:
   - `@model_validator(mode="after")` sets `database_url` to `sqlite:////data/budget.db` when `env == "production"` and the user has not provided an explicit `BUDGET_DATABASE_URL`.
   - Dev / test keep the current `sqlite:///data/budget.sqlite` default.
2. `src/budget_planner/web/app.py` lifespan hook: when `settings.env == "production"`, open a fresh connection and assert `PRAGMA wal_autocheckpoint;` returns `0`. Raise `RuntimeError` otherwise.
3. The assertion runs only in production so unit / integration tests on a dev settings instance do not need the pragma.

## Acceptance criteria

- `tests/unit/test_config.py::test_production_default_db_path`:
  - `Settings(_env_file=None, env="production", cookie_secret="x")` yields `database_url == "sqlite:////data/budget.db"`.
  - `BUDGET_DATABASE_URL` override wins.
- Dev / test defaults unchanged — existing tests stay green.

## Validation hook

```sh
just test tests/unit/test_config.py
just typecheck
```
