# ADR-0139: Canonical FX Converter: Cache-Only per Request, One Missing-Rate Policy, Explicit Live Refresh

- **Status**: Accepted
- **Date**: 2026-11-21
- **Amends**: [ADR-0006](0006-multi-currency-model.md) (fallback and fetch-on-demand clauses)
- **Relates to**: [ADR-0008](0008-transaction-amount-sign-and-direction.md), [ADR-0021](0021-functional-style-no-oop.md), [ADR-0130](0130-prevention-regime-and-full-architectural-compliance.md)
- **Finding**: Q-007 (G-01, A-06, C-02, C-17, F-06); task T-Q212; resolves OQ-13 and OQ-17 (defaults taken 2026-11-21, pending operator confirmation)

## Context

Four converter copies (`web/today_data.py`, `web/routers/forecast.py`, the budget and the analytics/ledger converters) applied five different missing-rate policies: rate 1, native amount, `None`, raise, and a stale-rate fallback. Page renders opened an `httpx.Client` and could block on the network. The live fetch could never succeed: the client was built without `base_url` while `_fetch_remote` requests the relative path `/<date>`, so httpx raised `UnsupportedProtocol` (not an `httpx.HTTPError`) before any I/O. The first non-PLN account would have turned all of this on.

## Decision

1. **One converter.** `services/fx.py` owns `FxConverter` (frozen dataclass) built per request by `fx.converter_for(conn, base_currency, today)`. Methods: `to_base(amount_minor, currency, on_date=None)` (historical, or reference-day rate) and `rate_for`. Identity (currency equals base) short-circuits with no lookup. Rounding is `ROUND_HALF_EVEN` at the destination exponent via `domain.money`. The old `convert`, `convert_cached` and `get_rate` (network) are deleted (OQ-13: dead code, no production caller of `convert`).
2. **Cache-only per request.** The converter reads `fx_rates` only. A rate is the exact-date row, else the latest row on or before the date (historical stale-rate rule of ADR-0006 stays, but is read-side only and never persisted under the requested date). No page render, router, view-model or `services/forecast.py` does network I/O (`purity` entries for Q-007 are deleted).
3. **One missing-rate policy: raise.** No cached rate on or before the date raises `FxUnavailableError`. Rate 1, the native amount, `0` and any magic fallback are forbidden. A surface may *omit* a figure it cannot compute (the ledger day header shows no net, T-D48); it may not substitute one. An unhandled `FxUnavailableError` is mapped by `web/errors.py` to HTTP 503 with a message naming the missing pair and the refresh command, never a 500.
4. **Live fetch is a separate explicit path.** `adapters/fx/frankfurter.py` owns the HTTP client factory `make_client(settings, transport=None)` (`base_url=settings.fx_api_url`, 5 s timeout; `transport` lets tests inject `httpx.MockTransport` into the same factory production uses) and `make_fetcher(client)`. `services/fx.refresh_rates(conn, fetch, on_date, base, currencies)` takes the fetcher as an injected port (`Callable[[date, str, str], Decimal]`), persists via `repositories/fx.upsert_rate`, and reports per-pair outcome. The entry point is `python -m budget_planner.cli.refresh_fx --db=<path> --currency EUR ...` (cron or operator). A UI button or in-app schedule is out of scope (needs an operator decision on cadence).
5. **Rate validation (OQ-17 default): in code, at the write and fetch boundary.** `parse_remote_rate` and `refresh_rates` reject `rate <= 0`, non-finite and non-numeric values; `upsert_rate` re-checks. No migration and no DB `CHECK` in this task (a `CHECK (rate > 0)` can follow as its own migration; recorded as pending operator confirmation).
6. **Data migration (OQ-1 default): none.** Prod is PLN-only with no `fx_rates` rows.

## Consequences

- Every aggregate (Today fortune, budget committed and spent, forecast, analytics, ledger strips) converts through the same object and fails the same way.
- Until rates are refreshed, a page that needs a missing pair returns 503 instead of showing a wrong number. Prod is unaffected (PLN only).
- `services/fx.py` and `services/forecast.py` no longer import `httpx`; the network edge is `adapters/fx`.
- Canonical row "FX conversion and rate lookup" is `exists` at zero copies.

## Alternatives considered

- Degrade to rate 1 or the native amount: rejected, silently wrong money (Q-007).
- Keep fetch-on-miss in the render path with a fixed client: rejected, blocks renders on a third party and breaks purity (ADR-0021).
- Stale-fallback persisted under the requested date: rejected, pollutes the cache (already refused in the original design).
