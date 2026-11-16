# T-D09 — Rate limit on auth routes

- **Phase**: 1 — App Prerequisites
- **Parallel-safe**: yes
- **Depends on**: T-D02 (auth routes, migration 0014's `auth_rate_limit` table)
- **References**: ADR-0072 (decision; amends ADR-0033 §2), ADR-0068 (architecture test), ADR-0070 (auth web layer)

## Deliverables

1. `repositories/rate_limit.py`:
   - `hit(conn, key, bucket_start) -> int`: an atomic UPSERT that returns the new count.
   - `prune(conn, before) -> int`: deletes stale buckets.
   - `get_count(conn, key, bucket_start) -> int`.
2. `services/rate_limit.py`:
   - `RateRule` and `RateDecision`, both frozen.
   - `bucket_start(now, window_seconds)`.
   - `consume(conn, scope, identity, rules, *, now)`: count first, then check, and prune on every write.
   - `audit_throttled(conn, ctx, *, scope, email)`: writes an `auth_event` audit row.
   - Rule builders read from `Settings`.
3. `config.py`: `rate_limit_enabled` plus per-route limits (`BUDGET_RATE_LIMIT_*`). Defaults are listed in ADR-0072 §2.
4. `web/routers/auth.py`: one rate-limit dependency on each of `POST /auth/login`, `POST /auth/login/finish` and `POST /auth/register/finish`. A throttled request gets 429 + `Retry-After`. The HTML form re-renders with `RATE_LIMITED_LOGIN_ERROR`. HTMX and JSON callers get `{"error": "rate_limited"}`. The clock can be injected through `app.state.rate_limit_clock` (used by tests).
5. `templates/auth/login.html`: shows the throttle message inside the existing error slot (`role="alert"`).
6. Architecture test: `rate_limit.py` is added to `NON_USER_SCOPED_REPOSITORIES`.

## Acceptance

- `tests/integration/web/test_auth_rate_limit.py`:
  - exceeding the limit returns 429 + `Retry-After` on all three routes;
  - after the window passes (injected clock), requests are allowed again;
  - separate keys (another email, another user) do not interfere;
  - a successful login still counts toward the limit;
  - the HTML and HTMX bodies match the spec;
  - a throttled request writes an audit row.
- `tests/unit/services/test_rate_limit.py`: bucket maths, retry-after, pruning, multiple rules, and the kill switch.
