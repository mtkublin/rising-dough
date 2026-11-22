# ADR-0141: One Amount Parser and Bounded Request Parameters

- **Status**: Accepted
- **Date**: 2026-11-21
- **Relates to**: [ADR-0006](0006-multi-currency-model.md), [ADR-0008](0008-transaction-amount-sign-and-direction.md), [ADR-0130](0130-prevention-regime-and-full-architectural-compliance.md)
- **Finding**: Q-023 (A-08, C-10, A-19, D-02, H3-03); task T-Q233

## Context

Seven hand-rolled amount parsers disagreed (`1e3`, `1_000`, non-ASCII digits, `12.345` rounding, `NaN`/`Infinity`/`1e400` crashes), year/month/id/page parameters were parsed with bare `int()`, magnitudes above SQLite int64 reached the database, and the pre-auth CSRF middleware raised on a non-ASCII token, a multipart body without boundary and more than 1000 form fields. Each surfaced as an HTTP 500.

## Decision

1. `domain/money.parse_amount_str` is the only amount parser; `parse_amount_minor` wraps it with `to_minor_units`. It accepts an optional sign, ASCII digits and one `.` or `,`; it rejects exponents, `NaN`/`Infinity`, underscores, non-ASCII digits, more fractional digits than the currency exponent, and any absolute value above `MAX_MINOR` (`10**15` minor units). Percent text is parsed by `parse_percent_str` (ASCII, bounded digits).
2. `web/params.py` owns request parameter parsing: `parse_date`, `parse_int` (ASCII, bounded, default ceiling `domain.limits.ID_MAX`), `parse_year_month` (raises `ParamError`, mapped to a visible 422 by `web/errors.py`), and the amount wrappers `positive_amount`, `credit_limit_amount`, `afford_amount_minor`. Routers keep no private parsers.
3. List filters degrade to "no filter" on bad text (lenient parsers); a bad `year`/`month` on `/budget` and malformed amounts are 422 with a message.
4. `CSRFMiddleware` compares tokens as UTF-8 bytes and answers 400 `malformed_form` for an unparseable or oversized form body.

## Consequences

- No input listed in the Q-023 repros returns 500. INV-5 is a plain passing test.
- Amount text over `MAX_MINOR` is rejected where it was previously stored.

## Amendment 2026-11-22 (operator decision; T-Q282)

Decision 3 is replaced for typed query parameters: every malformed `year`, `month`, date or integer query parameter returns 422 with a visible message on every route (`/plan`, `/ledger`, `/forecast`, `/budget`, `/today`, ...). There is no silent fallback to the current period and no "no filter" degradation. A missing parameter still takes its default. HTMX fragment routes answer with the error partial.

Enum-like query parameters follow the same rule (operator decision 2026-11-22, T-Q294, extends T-Q282): `/plan?tab=`, `/ledger?view=`, `/today?window=`, the analytics `period` and `/add?when=` (and any other choice parameter) return 422 naming the parameter on an unknown value. A missing or empty value still defaults.
