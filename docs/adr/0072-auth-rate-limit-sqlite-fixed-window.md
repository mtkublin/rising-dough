# ADR-0072: Auth Rate Limiting — In-House Fixed-Window Counters on `auth_rate_limit`

- **Status**: Accepted
- **Date**: 2026-11-03
- **Amends**: [ADR-0033](0033-v3-auth-single-user-passkey.md) §2 (limits and the `slowapi` choice)
- **Related**: T-D09, [ADR-0067](0067-auth-backend-sessions-and-passkey-challenges.md) (migration 0014 creates `auth_rate_limit`), [ADR-0068](0068-user-scoping-static-check-policy.md) (architecture test), [ADR-0070](0070-auth-web-layer-cookies-middleware-order.md) (auth routes, middleware order), T-D11 (Caddy in front)

## Context

ADR-0033 §2 asks for `slowapi` limits on the login routes. T-D02a's migration 0014 already created an `auth_rate_limit(id, key, bucket_start, count)` table with a unique index on `(key, bucket_start)`, so counters live in SQLite. That way they survive restarts and work in the single-container deployment.

`slowapi` wraps the `limits` package. Its storage backends are memory, Redis, Memcached and MongoDB. To use our table we would have to write a custom `limits.storage.Storage` subclass. We would also need the `@limiter.limit` decorator, which requires a `request` parameter and its own 429 handler registered in `web/app.py`. The decorator's key function cannot see the parsed form `email` without reading the body a second time. The job is "count hits per key per window in one table", and for that the library brings more surface than value.

## Decision

### 1. No new dependency: a small fixed-window limiter

- `repositories/rate_limit.py` owns the SQL:
  - `hit(conn, key, bucket_start)` runs one `INSERT … ON CONFLICT(key, bucket_start) DO UPDATE SET count = count + 1 RETURNING count`. It is a single atomic statement, so concurrent requests cannot lose an increment.
  - `prune(conn, before)` deletes buckets older than the longest window. Writes trigger it opportunistically, so no sweeper job is needed.
- `services/rate_limit.py` is pure policy:
  - `RateRule(limit, window_seconds)` is a frozen dataclass.
  - `bucket_start(now, window)` floors `now` to the window.
  - `consume(conn, scope, identity, rules, now=…)` increments every rule's bucket and returns a frozen `RateDecision(allowed, retry_after_seconds)`.
- The counter key is `"<scope>:<window>s:<identity>"`. The window is part of the key, so a minute bucket and an hour bucket that both start at `HH:00:00` never collide.
- **Count first, then check.** Every attempt counts, including attempts that are already throttled and attempts that end in a successful login. A success does not reset the counter, so it cannot be used to refill the budget. A blocked caller who keeps hammering keeps feeding the longer window, which is the behaviour we want against brute force.
- `retry_after_seconds` is the time left until the end of the latest-ending violated bucket, rounded up, with a minimum of 1.

### 2. Limits and keys (settings, all overridable via `BUDGET_RATE_LIMIT_*`)

| Route | Identity | Default rules |
|---|---|---|
| `POST /auth/login` | IP + normalised email | 5 / min, 20 / hour |
| `POST /auth/login` | IP (backstop against email spraying) | 100 / hour |
| `POST /auth/login/finish` | IP | 10 / min, 60 / hour |
| `POST /auth/register/finish` | user id | 5 / min, 20 / hour |

`rate_limit_enabled` (default `true`) is a kill switch for incident response. Tests tighten the limits by building `Settings(...)` themselves.

ADR-0033 §2 specified "3 attempts / 15 min per IP". That rule is replaced. A per-IP-only limit would let one attacker lock every user behind the same NAT out of the login page. Keying the tight limits on IP + email confines a lockout to one account from one network.

### 3. Wiring: a FastAPI dependency on each route, not middleware

Each of the three routes declares a dependency that returns a `RateDecision`. The handler returns early when `allowed` is false. A throttled request:

- returns **429** with `Retry-After: <seconds>`;
- on the HTML login form (no `HX-Request` and no JSON `Accept`), re-renders `auth/login.html` with one generic message. The message does not say whether the email exists;
- on HTMX and JSON clients, returns the body `{"error": "rate_limited"}`;
- writes one `audit_log` row: `entity_type='auth_event'`, `operation='create'`, payload `{event: "rate_limited", scope, email?}`, plus the request's IP and user agent.

Because the check sits inside the route, the credential check never runs on a throttled request. That also means bcrypt work is not spent on attackers.

Middleware order (ADR-0070 §6) is unchanged. CSRF still runs first, so a request without a valid token gets a 403 and never touches the counters.

### 4. Client IP and trusted proxies

The limiter uses `request.client.host` and never reads `X-Forwarded-For` itself.

In production, uvicorn runs with `--proxy-headers --forwarded-allow-ips=*` (Dockerfile, T-D10). uvicorn therefore rewrites `request.client` from `X-Forwarded-For`. This is safe only because the `app` container publishes no host ports (docker-compose, ADR-0032): its only peer is Caddy. Caddy (≥ 2.5) does not trust inbound `X-Forwarded-*` from clients unless `trusted_proxies` is configured, and neither Caddyfile configures it. So the header that reaches uvicorn holds the real client address, and a client cannot spoof it.

If the app port is ever published, or a second proxy hop is added, `--forwarded-allow-ips` must be narrowed to Caddy's address first. Recorded as a follow-up for the T-D10 / T-D11 owners. In dev the server binds `127.0.0.1`, so every client shares one key, which is fine for a single developer.

### 5. Architecture test exemption

`auth_rate_limit` is already listed as not user-owned (ADR-0068). `repositories/rate_limit.py` is added to `NON_USER_SCOPED_REPOSITORIES`, because its functions take `(conn, key, …)` and not `(conn, user_id, …)`.

## Consequences

- No new runtime dependency. About 150 lines of code that we own, and the tests inject a clock.
- Each limited request costs one or two extra single-row writes plus a prune `DELETE`. That is negligible for a single-user app. The table holds at most a few rows per active key per hour.
- Counters persist across restarts and deploys. A restart does not reset an attacker's budget.
- The fixed window allows a burst of up to 2× the limit across a window boundary. We accept this for login throttling.
- `fail2ban` on Caddy's access log (ADR-0033 §2) stays as the outer layer. The 429s now appear in that log.
