"""FX service: the one converter (ADR-0139, amends ADR-0006).

``converter_for`` reads the ``fx_rates`` cache once and returns an immutable
:class:`FxConverter`; page renders never touch the network. A missing rate
raises :class:`FxUnavailableError` (one policy: never rate 1, never the native
amount). Live rates arrive only through :func:`refresh_rates`, which takes the
fetcher as an injected port (``adapters/fx`` provides the httpx one).
"""

from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from bisect import bisect_right
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from budget_planner.domain.fx import FxFetchError, NewFxRate, RateFetcher
from budget_planner.domain.money import rescale_minor
from budget_planner.domain.transactions import Transaction
from budget_planner.repositories import fx as fx_repo

logger = logging.getLogger(__name__)


class HasBaseCurrency(Protocol):
    """The slice of ``Settings`` the converter needs (keeps services off ``config``)."""

    @property
    def base_currency(self) -> str: ...


@dataclass(frozen=True, slots=True)
class BaseCurrency:
    """A bare base-currency code as a :class:`HasBaseCurrency` (callers holding only the code)."""

    base_currency: str


class FxUnavailableError(RuntimeError):
    """No cached rate for a pair on or before the requested date (ADR-0139)."""


@dataclass(frozen=True, slots=True)
class RateSeries:
    """Cached rates of one source currency into base, ascending by date."""

    dates: tuple[dt.date, ...]
    rates: tuple[Decimal, ...]


@dataclass(frozen=True, slots=True)
class FxConverter:
    """Cache-only converter into ``base_currency`` (built per request)."""

    base_currency: str
    today: dt.date
    series: Mapping[str, RateSeries]

    def rate_for(self, currency: str, on_date: dt.date | None = None) -> Decimal:
        """Latest cached ``currency -> base`` rate on or before ``on_date`` (default today)."""
        if currency == self.base_currency:
            return Decimal(1)
        day = self.today if on_date is None else on_date
        found = self.series.get(currency)
        idx = bisect_right(found.dates, day) - 1 if found is not None else -1
        if found is None or idx < 0:
            raise FxUnavailableError(
                f"no cached FX rate {currency}->{self.base_currency} on or before {day}; "
                "run `python -m budget_planner.cli.refresh_fx`"
            )
        return found.rates[idx]

    def to_base(self, amount_minor: int, currency: str, on_date: dt.date | None = None) -> int:
        """``amount_minor`` of ``currency`` in base-currency minor units."""
        if currency == self.base_currency:
            return amount_minor
        return rescale_minor(
            amount_minor, currency, self.base_currency, self.rate_for(currency, on_date)
        )


def build_converter(
    base_currency: str, today: dt.date, rates: Iterable[tuple[str, dt.date, Decimal]]
) -> FxConverter:
    """Pure builder: ``rates`` are ``(from_ccy, date, rate)`` into ``base_currency``."""
    grouped: dict[str, list[tuple[dt.date, Decimal]]] = {}
    for ccy, day, rate in sorted(rates, key=lambda r: (r[0], r[1])):
        grouped.setdefault(ccy, []).append((day, rate))
    series = {
        ccy: RateSeries(tuple(d for d, _ in pairs), tuple(r for _, r in pairs))
        for ccy, pairs in grouped.items()
    }
    return FxConverter(base_currency=base_currency, today=today, series=series)


def converter_for(
    conn: sqlite3.Connection,
    settings: HasBaseCurrency,
    today: dt.date,
    *,
    base_currency: str | None = None,
) -> FxConverter:
    """Read the rate cache once and build the request's converter (no network)."""
    base = base_currency or settings.base_currency
    cached = fx_repo.list_rates_to(conn, base)
    return build_converter(base, today, ((r.from_ccy, r.date, r.rate) for r in cached))


def txn_base_of(
    converter: FxConverter, currency_by_account: Mapping[int, str]
) -> Callable[[Transaction], int]:
    """Return ``txn -> base minor`` at the rate on the txn's own date (ADR-0006, ADR-0139)."""

    def _to_base(txn: Transaction) -> int:
        ccy = currency_by_account.get(txn.account_id, converter.base_currency)
        return converter.to_base(txn.amount, ccy, txn.operation_date)

    return _to_base


@dataclass(frozen=True, slots=True)
class RefreshOutcome:
    """Result of refreshing one ``from_ccy -> to_ccy`` pair."""

    from_ccy: str
    to_ccy: str
    rate: Decimal | None
    error: str | None


def refresh_rates(
    conn: sqlite3.Connection,
    fetch: RateFetcher,
    on_date: dt.date,
    base_currency: str,
    currencies: Iterable[str],
) -> tuple[RefreshOutcome, ...]:
    """Fetch and cache ``currency -> base`` for ``on_date``; one outcome per distinct currency.

    A failed or invalid answer (``rate <= 0``) is reported, never stored, and does
    not stop the other pairs.
    """
    outcomes: list[RefreshOutcome] = []
    for ccy in sorted({c for c in currencies if c != base_currency}):
        try:
            rate = fetch(on_date, ccy, base_currency)
            fx_repo.upsert_rate(
                conn, NewFxRate(date=on_date, from_ccy=ccy, to_ccy=base_currency, rate=rate)
            )
        except (FxFetchError, ValueError) as exc:
            logger.warning("fx refresh %s->%s failed: %s", ccy, base_currency, exc)
            outcomes.append(RefreshOutcome(ccy, base_currency, None, str(exc)))
        else:
            outcomes.append(RefreshOutcome(ccy, base_currency, rate, None))
    return tuple(outcomes)


__all__ = [
    "FxConverter",
    "FxUnavailableError",
    "HasBaseCurrency",
    "RateSeries",
    "RefreshOutcome",
    "build_converter",
    "converter_for",
    "refresh_rates",
    "txn_base_of",
]
