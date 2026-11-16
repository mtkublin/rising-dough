# T-D03 — Config surface for production

- **Phase**: 1 — App Prerequisites
- **Parallel-safe**: yes
- **Depends on**: nothing
- **Blocks**: T-D04 (DB path depends on `env`), T-D07 (headers middleware consumes `trusted_hosts`), T-D23 (cloud-init renders these into compose env)
- **References**: ADR-0032 §5, ADR-0033 §5

## Context

v1 only needed `database_url`, `base_currency`, `display_timezone`, `host`, `port`, `fx_api_url`. v3 adds:

- a named deployment environment (`dev` / `test` / `production`) that gates production-only assertions (ADR-0034 §2),
- a canonical bind pair (`bind_host`, `bind_port`) with a loopback-only guard carried over from ADR-0005,
- a configurable `trusted_hosts` list for Starlette's `TrustedHostMiddleware` (added later by T-D07),
- a required `cookie_secret` in production for signed-session cookies,
- a bounded `session_lifetime_days`.

The old field names `host` / `port` are retired. Every caller that read `settings.host` now reads `settings.bind_host`; same for `port`.

## Deliverables

1. `src/budget_planner/config.py` fields added / renamed:
   - `env: Literal["dev", "test", "production"] = "dev"` (`BUDGET_ENV`).
   - `bind_host: str = "127.0.0.1"` — replaces `host`. Keeps the `_reject_public_bind` validator.
   - `bind_port: int = 8000` — replaces `port`.
   - `trusted_hosts: tuple[str, ...] = ()` — parsed from comma-separated `BUDGET_TRUSTED_HOSTS`.
   - `cookie_secret: str` — required in production (raises `ValidationError` on startup when `env == "production"` and the value is empty). Dev / test default to a known dev value and emit a one-shot warning.
   - `session_lifetime_days: int = 14` — bounded 1..90.
2. `.env.example` updated to list the new keys (and drops `BUDGET_HOST` / `BUDGET_PORT`).
3. Every call site under `src/` and `tests/` migrated from `host` / `port` to `bind_host` / `bind_port`.

## Acceptance criteria

- `tests/unit/test_config.py` covers:
  - defaults (`env == "dev"`, `bind_host == "127.0.0.1"`, `bind_port == 8000`, `trusted_hosts == ()`),
  - `BUDGET_TRUSTED_HOSTS` CSV parsing,
  - production without `cookie_secret` raises,
  - dev without `cookie_secret` uses the dev default and does not raise,
  - `session_lifetime_days` out of bounds raises.
- `grep -nR "settings\.host\b" src tests` returns no hits.
- `BUDGET_BIND_HOST=0.0.0.0` still rejected via the loopback guard.

## Validation hook

```sh
just test tests/unit/test_config.py
just lint
just typecheck
```

All green.
