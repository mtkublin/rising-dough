# ADR-0006: Multi-Currency Model

- **Status**: Accepted
- **Date**: 2026-10-23

## Context

The user operates accounts in different currencies and wants a unified fortune / budget / forecast view.

## Decision

- Each `account` has an immutable `currency` (ISO 4217) set at creation.
- Each `transaction` inherits the currency of its `account_id` (no `currency` column on `transactions`).
- A `base_currency` is configured in app config (default `PLN`). All aggregates (fortune, budget, forecast, analytics) are expressed in base currency.
- FX rates fetched from the ECB via `frankfurter.app` on demand, cached in a local `fx_rates(date, from_ccy, to_ccy, rate)` table.
- Conversion uses the **historical rate**: a transaction dated `2026-01-15` converts at the `2026-01-15` rate, not today's.
- Fallback: if the API is unreachable and no rate for the requested date is cached, use the most recent known rate for that pair with a log warning.
- Amounts stored as **positive integer minor units** of the account's currency (e.g. PLN grosz, EUR cents). Signed display derived from `category.direction`.

## Cross-currency transits

- Blocked at the service/validation layer in v1. A transit must reference `account_id` and `dest_account_id` with the same currency.
- Rationale: real-world cross-currency transits involve bank-specific FX spreads that cannot be modelled accurately without extra fields and UX. Deferred to a future ADR.

## Consequences

- Clean separation: accounts own currency, transactions do not.
- Historical reports stay stable; today's FX movements do not retroactively rewrite past aggregates.
- Base currency can be changed with no data migration (recomputed on read).

## Alternatives Considered

- **Single currency**: simpler, rejected because the user maintains multi-currency accounts.
- **`currency` on transaction**: necessary only if accounts hold mixed currencies (rare); over-models the common case.
- **Live rate for all conversions**: wrong signal; historical charts would wiggle on today's FX moves.
- **Manual rate entry**: operationally painful.

## Amendment 2026-11-21 (T-Q216, Q-011, Q-029): one renderer and a complete exponent table

- `domain/money.py:minor_to_major(amount, currency)` is the only minor-to-major conversion. Templates use the `money` / `money_num(currency)` filters; services and routers call `minor_to_major` (or `major_float` for chart geometry only). Literal `/ 100`, `/ 100.0`, `* 100` and two-decimal money formats are banned outside `domain/money.py` (guards G6, G27).
- The exponent table is `CURRENCY_EXPONENTS`, built beside `ISO_4217_CURRENCIES` from ISO 4217: every offered code has an explicit entry (0 for BIF, CLP, DJF, GNF, ISK, JPY, KMF, KRW, PYG, RWF, UGX, VND, VUV, XAF, XOF, XPF; 3 for BHD, IQD, JOD, KWD, LYD, OMR, TND; otherwise 2). Codes outside the list fall back to 2. A unit test fails when an offered code lacks an entry.
- Rounding policy: major to minor rounds half up (`Decimal.ROUND_HALF_UP`) at the currency exponent; minor to major is exact (no rounding); integer splits of a minor amount go through `divide_minor_units` (floor). T-Q229 may refine the clock/period side but not these rules.
- Percent and basis-point scaling (`bps_to_percent`, `percent_to_bps`) lives in the same module because it is the only other `x100` scale in the app.
- OQ-1 default: prod is PLN-only with no fx rows, so no data migration is needed; the exponent changes only affect codes that are not yet in use.

## Amendment 2026-11-21 (T-Q229, Q-031, Q-076, ADR-0140): one rounding helper module and the timestamp format

- `domain/money.py` owns the rounding primitives: `round_div(numerator, denominator, *, mode)` (integer ratio to the nearest integer) and `round_scaled(value, *, mode)` (a `Decimal` to the nearest integer). `mode` is an explicit argument, `HALF_EVEN` or `HALF_UP` (exported constants; callers never name `ROUND_HALF_*` or call `.quantize` outside `domain/money.py`, guards G6, G27). `rescale_minor`, `to_minor_units`, `percent_to_bps` and the display rounding call them.
- **No behaviour change.** Each call site keeps the mode it had before this amendment (the audit text said HALF_EVEN everywhere; the code and its pinned tests did not):

  | Site | Mode |
  |---|---|
  | `domain/money.py` `to_minor_units`, `percent_to_bps`, display rounding | HALF_UP |
  | `domain/money.py` `rescale_minor` (FX rounding point, ADR-0139) | HALF_EVEN |
  | `services/recurring_formula.py` `_apply_coefficient` (T-Q222 ties pinned) | HALF_UP |
  | `services/balance.py` average, `services/analytics.py` monthly average, `services/budget.py` (average, per-day), `services/forecast.py` per-day split, `services/today.py` per-day | HALF_EVEN |

  Unifying to a single mode is an operator question: **OQ-ROUND** (single rounding mode? default kept per-site 2026-11-21, pending operator confirmation).
- Stored timestamps are UTC text `YYYY-MM-DDTHH:MM:SS.mmmZ` (millisecond precision, equal to SQLite's `strftime('%Y-%m-%dT%H:%M:%fZ','now')`), produced in Python by `clock.utc_now_iso()` / `clock.iso_utc()`. Retention and undo-window cutoffs are computed in Python in the same format; nothing compares a stored timestamp with `datetime('now', ...)`.
