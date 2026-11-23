# ADR-0146: An FX Freshness Health Path for the External Monitor

- **Status**: Accepted
- **Date**: 2026-11-22
- **Relates to**: [ADR-0119](0119-replication-freshness-health-path.md) (same shape), [ADR-0145](0145-nbp-table-a-daily-fx-refresh-in-app-task.md), [ADR-0139](0139-canonical-fx-converter-cache-only-one-missing-rate-policy.md), [ADR-0033](0033-auth-session-model.md) section 5, [ADR-0140](0140-canonical-clock-and-today-dependency.md)
- **Task**: T-Q292 (operator decision 2026-11-22, Q39)

## Context

ADR-0145 made the FX cache refresh itself, and failures are only a log line (`fx_refresh_failed`). If NBP changes its payload, the host loses egress or the task dies, rates go stale and the first symptom is a 503 page (`FxUnavailableError`) for a foreign-currency account. `/health` and `/ready` stay green. Like the replication stall of ADR-0119, nobody would be told. The external monitor (UptimeRobot) can only see a non-2xx status on a public URL.

## Decision

1. **Endpoint `GET /health/fx`** (and `HEAD`) in `web/routers/health.py`: public, no auth, exempt from the auth and must-change-password middleware like `/health/replication`. It reads the DB and **never writes**. The decision is a pure function in `services/fx_health.py` (`evaluate`), mirroring `services/replication_health.py`; the router opens a connection, calls one service function and returns the verdict.
2. **Rule.** For every non-base currency used by a **live** account (`deleted_at IS NULL`), take the newest cached `currency -> base` rate date. Age is whole calendar days between `today_local(settings)` (display timezone, ADR-0140) and that date (a rate dated in the future counts as age 0).

   | Case | HTTP | `status` |
   |------|------|----------|
   | every used currency has a rate at most `fx_max_rate_age_days` old | 200 | `ok` |
   | refresh not active (`daily_refresh_active()` false), or no live account uses a foreign currency (so a production deployment started with refresh switched off is not alerted; that is an explicit operator choice) | 200 | `disabled` |
   | some used currency's newest rate is older than the limit | 503 | `stale` |
   | some used currency has no rate at all (wins over `stale`) | 503 | `never` |
   | any other state, or an exception while reading | 503 | `error` |

   Fail closed: nothing unknown is healthy. A failure is logged server side (`fx_health_failed`) and never echoed.
3. **Threshold: `fx_max_rate_age_days`** (`BUDGET_FX_MAX_RATE_AGE_DAYS`, default 4, range 1 to 60). NBP publishes on business days only: a Friday table is 3 days old on Monday morning before the 12:30 refresh, and one holiday adds a day. 4 calendar days covers a weekend plus one holiday, and a failing refresh surfaces on the next day it should have worked.
4. **Body**: `status`, `currencies` (a list of `{code, newest_date, age_days}`, sorted by code, `newest_date` and `age_days` null when never), `max_age_days`, `checked_at` (UTC ISO). No amounts, no account or user data beyond ISO currency codes.
5. **User scoping (deliberate).** The check is a host-level health check, not a user view, so it counts the live accounts of **all users**: a second user's USD account makes USD a used currency. The service lists the live users (`users.list_live`) and reads each one's live accounts through the ordinary user-scoped `accounts.list_all`, then looks up the newest rate per code in the global `fx_rates` table; no unscoped SQL, so no allowlist entry. Only currency codes and dates reach the response. Account currencies are three characters (DB constraint) validated as ISO 4217 codes on creation.
6. **No new infrastructure.** The path is a JSON response behind the existing catch-all `reverse_proxy`; no Terraform, Caddy or host change; no new secret. Same rate-limit and CSP notes as ADR-0119 section 8.
7. **Operator step (not done by the agent).** Add a third UptimeRobot monitor: plain HTTP(s) status-code monitor (no keyword), `https://budget.rising-dough.eu/health/fx`, every 5 minutes, "up" = HTTP 2xx, same alert contact as `/health`. The free plan monitors with HEAD; the route answers HEAD with the same status.
8. **Related hardening of the refresh itself** (same task, recorded as the ADR-0145 amendment 2026-11-22): same-day hourly retry until 18:00 Europe/Warsaw, and whole-table rejection of a stale table (`fx_max_table_age_days`, default 7).

## Consequences

- A broken refresh becomes an alert about 4 days after the last good table, instead of a 503 page for the user. It is a slow alarm by design (weekends, holidays); the hourly same-day retry (ADR-0145) handles short provider outages before that.
- In dev and test (refresh not active) the path is always 200 `disabled`, so no environment other than production alerts.
- A deployment with only PLN accounts is `disabled`: nothing needs a rate.
- A newly added foreign account with no cached rate turns the monitor red (`never`) until the next refresh, which is the intended signal.

## Alternatives considered

- Read the log for `fx_refresh_failed`: the monitor cannot see logs.
- Alert on the age of the newest rate of any currency: hides a single missing currency (rates for one code can be absent while the table is fresh).
- Per-user check behind auth: the external monitor has no session.

## Amendment 2026-11-22 (T-Q307): disabled in production is a failure

Operator decision (deferred question 45): the daily NBP refresh is on in production and a production deployment with it switched off must alert.

1. **Production enables the refresh explicitly.** The compose template sets `BUDGET_FX_REFRESH_ENABLED: "true"` on the app service, so the setting no longer rests on the `None` default (`daily_refresh_active()` is true in production anyway). NBP egress from the host needs no firewall change (confirmed earlier).
2. **Disabled in production is 503.** When `Settings.env == "production"` and `daily_refresh_active()` is false, `GET /health/fx` answers 503 with `status: "disabled"` (same body shape, empty `currencies`), so the UptimeRobot monitor alerts. This supersedes the section 2 row that made it 200 and the "explicit operator choice" remark. Outside production (dev, test) refresh-off stays 200 `disabled`. Production is detected by `Settings.env == "production"`, the same switch as the bcrypt floor (T-Q291) and the other production validators.
3. **Enabled with no foreign account is 200 `ok`.** With the refresh active and no live account in a foreign currency (PLN-only prod today), nothing needs a rate: 200 `ok` with `currencies: []` (the refresh keeps fetching). `disabled` now means only "refresh not active".

Updated table:

| Case | HTTP | `status` |
|------|------|----------|
| refresh not active, not production | 200 | `disabled` |
| refresh not active, production | 503 | `disabled` |
| refresh active, no live foreign account, or all used currencies fresh | 200 | `ok` |
| stale / never / error | 503 | `stale` / `never` / `error` |

Operator step after deploy: add the UptimeRobot monitor on `/health/fx` (section 7); it is not yet in place.
