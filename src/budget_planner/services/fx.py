"""FX service (T-020).

Resolve historical FX rates with local SQLite caching, remote fetch from
``frankfurter.app`` on cache miss, and a stale-fallback to the most recent
known rate when the API is unreachable (ADR-0006).

The service is a pure function of the DB cache + remote state. The HTTP
client is passed in (never constructed here) so routers can share a single
lifespan-scoped client.
"""

from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

import httpx

from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.money import currency_decimals
from budget_planner.repositories import fx as fx_repo

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT = 5.0


class FxUnavailableError(RuntimeError):
    """Raised when neither remote nor local cache can produce a rate."""


def _parse_remote_rate(payload: object, to_ccy: str) -> Decimal:
    """Pull ``rates[to_ccy]`` out of a frankfurter response as a Decimal.

    Raises ``KeyError`` / ``TypeError`` / ``InvalidOperation`` on malformed input.
    """
    if not isinstance(payload, dict):
        raise TypeError("fx payload is not an object")
    rates = payload.get("rates")
    if not isinstance(rates, dict):
        raise KeyError("fx payload missing 'rates'")
    value = rates[to_ccy]
    # Always via str() to avoid float drift (ADR-0006 risk note).
    return Decimal(str(value))


def _fetch_remote(
    http: httpx.Client,
    on_date: dt.date,
    from_ccy: str,
    to_ccy: str,
) -> Decimal:
    response = http.get(
        f"/{on_date.isoformat()}",
        params={"from": from_ccy, "to": to_ccy},
        timeout=_HTTP_TIMEOUT,
    )
    response.raise_for_status()
    return _parse_remote_rate(response.json(), to_ccy)


def _fallback(
    conn: sqlite3.Connection,
    on_date: dt.date,
    from_ccy: str,
    to_ccy: str,
) -> Decimal:
    latest = fx_repo.latest_rate(conn, from_ccy, to_ccy, on_or_before=on_date)
    if latest is None:
        raise FxUnavailableError(f"no cached FX rate for {from_ccy}->{to_ccy} on/before {on_date}")
    logger.warning(
        "fx fallback: %s->%s on %s uses stale rate from %s",
        from_ccy,
        to_ccy,
        on_date,
        latest.date,
    )
    return latest.rate


def get_rate(
    conn: sqlite3.Connection,
    http: httpx.Client,
    on_date: dt.date,
    from_ccy: str,
    to_ccy: str,
) -> Decimal:
    """Return the FX rate from ``from_ccy`` to ``to_ccy`` for ``on_date``.

    - Identity: ``get_rate(..., ccy, ccy) == Decimal("1")`` (no cache or HTTP touched).
    - Cache hit: returned verbatim; HTTP skipped.
    - Cache miss: fetches remote, persists under ``on_date``, returns the rate.
    - Remote failure (HTTP error, non-200, missing key): logs a warning and returns
      the most recent cached rate on-or-before ``on_date``. Stale rates are NOT
      persisted under ``on_date`` to avoid polluting the cache.
    - No cached rate on failure: raises ``FxUnavailableError``.
    """
    if from_ccy == to_ccy:
        return Decimal("1")

    hit = fx_repo.find_rate(conn, on_date, from_ccy, to_ccy)
    if hit is not None:
        return hit.rate

    try:
        rate = _fetch_remote(http, on_date, from_ccy, to_ccy)
    except (httpx.HTTPError, KeyError, TypeError, ValueError, InvalidOperation):
        return _fallback(conn, on_date, from_ccy, to_ccy)

    fx_repo.upsert_rate(
        conn,
        NewFxRate(date=on_date, from_ccy=from_ccy, to_ccy=to_ccy, rate=rate),
    )
    return rate


def convert(  # noqa: PLR0917
    conn: sqlite3.Connection,
    http: httpx.Client,
    amount_minor: int,
    on_date: dt.date,
    from_ccy: str,
    to_ccy: str,
) -> int:
    """Convert ``amount_minor`` using the historical rate for ``on_date``.

    Rounds to the destination currency's minor-unit scale with
    ``ROUND_HALF_EVEN``. Sign is preserved. Identity short-circuits.
    """
    if from_ccy == to_ccy:
        return amount_minor
    rate = get_rate(conn, http, on_date, from_ccy, to_ccy)
    src_decimals = currency_decimals(from_ccy)
    dst_decimals = currency_decimals(to_ccy)
    # Minor-unit → major by src_decimals, convert, re-scale to dst minor.
    src_scale = Decimal(10) ** src_decimals
    dst_scale = Decimal(10) ** dst_decimals
    major = Decimal(amount_minor) / src_scale
    converted = (major * rate) * dst_scale
    quantised = converted.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
    return int(quantised)


def convert_cached(
    conn: sqlite3.Connection,
    amount_minor: int,
    on_date: dt.date,
    from_ccy: str,
    to_ccy: str,
) -> int:
    """Like :func:`convert` but never touches the network (page-render safe).

    Uses the exact-date cached rate, else the latest cached rate on or before
    ``on_date``; raises ``FxUnavailableError`` when nothing is cached.
    """
    if from_ccy == to_ccy:
        return amount_minor
    hit = fx_repo.find_rate(conn, on_date, from_ccy, to_ccy)
    rate = hit.rate if hit is not None else _fallback(conn, on_date, from_ccy, to_ccy)
    major = Decimal(amount_minor) / (Decimal(10) ** currency_decimals(from_ccy))
    converted = major * rate * (Decimal(10) ** currency_decimals(to_ccy))
    return int(converted.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


__all__ = ["FxUnavailableError", "convert", "convert_cached", "get_rate"]
