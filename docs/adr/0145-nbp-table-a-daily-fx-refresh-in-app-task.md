# ADR-0145: NBP Table A as the FX Source, Refreshed by an In-App Daily Task

- **Status**: Accepted
- **Date**: 2026-11-22
- **Amends**: [ADR-0139](0139-canonical-fx-converter-cache-only-one-missing-rate-policy.md) (refresh path and provider); supersedes the ECB/frankfurter source named in `requirements.md` F7.4 and ADR-0006
- **Relates to**: [ADR-0021](0021-functional-style-no-oop.md), [ADR-0078](0078-v3-data-protection-controls.md) section 7 (retention task shape), [ADR-0099](0099-release-and-environment-policy.md), [ADR-0140](0140-canonical-clock-and-today-dependency.md)
- **Finding**: FX cache (F7.4); task T-Q290 (operator decision 2026-11-22)

## Context

ADR-0139 made page renders cache-only, so rates only change when something refreshes the cache. The only refresh path was the operator CLI over frankfurter.app (ECB). The cache therefore went stale unless a human ran the CLI. The base currency is PLN, and the National Bank of Poland (NBP) publishes the official PLN mid rates for about 30 currencies (table A) every business day around noon, with no API key.

## Decision

1. **Source: NBP table A** (`GET https://api.nbp.pl/api/exchangerates/tables/A/?format=json`). A mid rate is PLN per one unit of the currency, so a row is stored as `(effectiveDate, code, PLN, mid)`. Because NBP quotes PLN only, a refresh with `base_currency != "PLN"` is refused with a logged error. The frankfurter adapter and the per-pair `RateFetcher` port are removed.
2. **Port**: `domain/ports.RateSource` (`latest_table() -> RateTable | None`), `RateTable` in `domain/fx.py`. The httpx adapter is `adapters/fx/nbp.py` (the only module that talks HTTP for FX; `make_client` is the single client factory, `base_url = settings.fx_api_url`, default `https://api.nbp.pl`). Network happens only through the injected port (ADR-0021).
3. **Strict validation** in the adapter: payload is a one-element list whose table is `A`; `effectiveDate` is an ISO date; every row has a three-letter code and a finite `mid > 0` parsed through `str` (no float drift); duplicate codes reject the payload. Codes outside `ISO_4217_CURRENCIES` are skipped and logged, not stored. A malformed payload raises `FxFetchError`; nothing is written. The service additionally rejects an effective date later than today (display timezone). HTTP 404 ("no data", NBP's answer for a date without a table) is `None`: the cache keeps the last rates.
4. **One service function**: `services/fx.refresh_from_source(conn, source, today, base_currency, currencies=None)` stores one row per currency under the table's effective date in one `db_transaction`. It inserts only rows that are new, updates a row only when its rate differs, and leaves equal rows alone, so a second run is a no-op. The CLI (`python -m budget_planner.cli.refresh_fx --db=<path>`) and the daily task both call it.
5. **In-app daily background task** `web/fx_refresh_task.py`, started and stopped in the app lifespan beside `retention_task`. It runs **once a day after 12:30 Europe/Warsaw** (display timezone; NBP publishes around noon) and **once at startup when the cache has no rate dated today**. The schedule arithmetic is pure (`domain/fx_schedule.py`: `next_run_at`, `is_due`) and computed in local wall-clock time, so it is exact across DST changes. Failures (`FxFetchError`, sqlite errors) are logged as `fx_refresh_failed` and never stop the loop; the cache keeps the last rates and page renders stay cache-only.
6. **Toggle**: `BUDGET_FX_REFRESH_ENABLED` (`Settings.fx_refresh_enabled`, tri-state). Unset means on in `production` and off in `dev` and `test`; an explicit value wins.
7. **Host**: no host timer and no Terraform change. The instance security group has `outbound_default_policy = "accept"` and `DOCKER-USER` only drops the metadata address (ADR-0111 section 6), so `api.nbp.pl:443` is already reachable. Agents never `terraform apply` prod (ADR-0099).

## Consequences

- The cache refreshes itself on business days; weekends and holidays keep the last table (the converter already uses the latest rate on or before a date).
- A restart on a weekend triggers one idempotent fetch (no row is dated today); it writes nothing new.
- A source outage leaves stale but valid rates; the failure is a structured log line, not a 503.
- Only PLN-base deployments can refresh. A second base currency would need a new ADR and a cross-rate source.

## Alternatives considered

- Host systemd timer calling the CLI: needs a Terraform and host-agent change and an operator apply (rejected, no-host-change decision).
- Keep ECB/frankfurter: not the official PLN rate and per-pair requests.
- Fetch on page render: violates ADR-0139.
