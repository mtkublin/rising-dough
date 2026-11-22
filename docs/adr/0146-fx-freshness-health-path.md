# ADR-0146: FX Freshness Health Path for the External Monitor

- **Status**: Accepted
- **Date**: 2026-11-22
- **Relates to**: ADR-0119, ADR-0139, ADR-0145, ADR-0033
- **Task**: T-Q292

## Context

The daily NBP refresh (ADR-0145) logs failures and leaves the cache untouched (ADR-0139: page renders are cache-only). A silent run of failures would leave stale rates with nobody noticing, the same blind spot ADR-0119 closed for replication. The external monitor (UptimeRobot) only sees status codes.

## Decision (operator, 2026-11-22)

1. **Retry.** A failed daily run is retried the same day (hourly until 18:00 Europe/Warsaw), then waits for the next day.
2. **Backdated tables rejected.** A table whose effective date is older than N days (setting, default 7) is rejected, so a backdated payload cannot rewrite history.
3. **Endpoint `GET /health/fx`**, public and exempt from auth like `/health/replication`; no DB writes; fail closed. The decision is a pure function in `services/` (clock and settings as arguments).

   | Case | Status | `status` |
   |------|--------|----------|
   | newest cached rate of every non-base currency in use is at most N business days old (setting) | 200 | `ok` |
   | refresh disabled, or no foreign currency in use | 200 | `disabled` |
   | a currency in use has an older newest rate | 503 | `stale` |
   | a currency in use has no cached rate | 503 | `never` |
   | any unknown state | 503 | fail closed |

4. **Monitor.** The operator adds an UptimeRobot status-code monitor on `https://budget.rising-dough.eu/health/fx`, 5 min, same alert contact (operator step, as ADR-0119 §6).

## Consequences

- A stalled refresh pages the operator within the staleness window.
- Retry plus backdate rejection amend ADR-0145 (see its amendment 2026-11-22).
