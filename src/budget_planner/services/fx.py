"""FX service: the one converter (ADR-0139, amends ADR-0006).

``converter_for`` reads the ``fx_rates`` cache once and returns an immutable
:class:`FxConverter`; page renders never touch the network. A missing rate
raises :class:`FxUnavailableError` (one policy: never rate 1, never the native
amount). Live rates arrive only through :func:`refresh_from_source`, which takes the
``RateSource`` as an injected port (``adapters/fx/nbp`` provides the httpx one; ADR-0145).
"""

from __future__ import annotations

import datetime as dt
import logging
import sqlite3
from bisect import bisect_right
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Final, Protocol

from budget_planner.domain.fx import (
    DEFAULT_MAX_TABLE_AGE_DAYS,
    FxFetchError,
    FxRate,
    NewFxRate,
    StaleRateTableError,
    validate_rate,
)
from budget_planner.domain.money import rescale_minor
from budget_planner.domain.ports import RateSource
from budget_planner.domain.transactions import Transaction
from budget_planner.repositories import accounts as accounts_repo, fx as fx_repo
from budget_planner.repositories._shared import transaction as db_transaction

logger = logging.getLogger(__name__)

NBP_BASE: Final = "PLN"


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

    def to_currency(
        self, amount_minor: int, from_ccy: str, to_ccy: str, on_date: dt.date | None = None
    ) -> int:
        """``amount_minor`` of ``from_ccy`` in ``to_ccy`` minor units, pivoting through base."""
        if from_ccy == to_ccy:
            return amount_minor
        in_base = self.to_base(amount_minor, from_ccy, on_date)
        if to_ccy == self.base_currency:
            return in_base
        inverse = Decimal(1) / self.rate_for(to_ccy, on_date)
        return rescale_minor(in_base, self.base_currency, to_ccy, inverse)


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


def currency_by_account(
    conn: sqlite3.Connection, user_id: int, *, include_deleted: bool = False
) -> dict[int, str]:
    """``account_id -> currency``; live accounts only unless ``include_deleted`` (ADR-0136)."""
    accounts = accounts_repo.list_all(conn, user_id, include_deleted=include_deleted)
    return {a.id: a.currency for a in accounts}


def txn_base_of(
    converter: FxConverter, currency_by_account: Mapping[int, str]
) -> Callable[[Transaction], int]:
    """Return ``txn -> base minor`` at the rate on the txn's own date (ADR-0006, ADR-0139)."""

    def _to_base(txn: Transaction) -> int:
        ccy = currency_by_account.get(txn.account_id, converter.base_currency)
        return converter.to_base(txn.amount, ccy, txn.operation_date)

    return _to_base


@dataclass(frozen=True, slots=True)
class RefreshResult:
    """What one refresh stored, all under the table's ``effective_date`` (ADR-0145)."""

    effective_date: dt.date
    inserted: tuple[str, ...]
    updated: tuple[str, ...]
    unchanged: tuple[str, ...]


def _store_rate(
    conn: sqlite3.Connection, day: dt.date, code: str, base_currency: str, rate: Decimal
) -> str:
    """Insert, update or leave one cached rate; returns which of the three it was."""
    validate_rate(rate)
    existing = fx_repo.find_rate(conn, day, code, base_currency)
    if existing is not None and existing.rate == rate:
        return "unchanged"
    fx_repo.upsert_rate(conn, NewFxRate(date=day, from_ccy=code, to_ccy=base_currency, rate=rate))
    return "inserted" if existing is None else "updated"


def refresh_from_source(
    conn: sqlite3.Connection,
    source: RateSource,
    today: dt.date,
    base_currency: str,
    currencies: Iterable[str] | None = None,
    *,
    max_table_age_days: int = DEFAULT_MAX_TABLE_AGE_DAYS,
) -> RefreshResult | None:
    """Cache the source's latest table (``currency -> base``); ``None`` when it has no data.

    Inserts only new ``(date, from, to)`` rows and updates a row only when its
    rate differs, so a second run is a no-op. Raises :class:`FxFetchError` when
    the provider fails, its table is dated after ``today``, more than
    ``max_table_age_days`` before it (:class:`StaleRateTableError`) or
    ``base_currency`` is not PLN (NBP quotes PLN only); nothing is stored then.
    """
    if base_currency != NBP_BASE:
        raise FxFetchError(f"NBP table A quotes {NBP_BASE} only, base currency is {base_currency}")
    table = source.latest_table()
    if table is None:
        return None
    if table.effective_date > today:
        raise FxFetchError(f"rate table dated {table.effective_date} is after today {today}")
    if (today - table.effective_date).days > max_table_age_days:
        raise StaleRateTableError(
            f"rate table dated {table.effective_date} is more than {max_table_age_days} days "
            f"before today {today}"
        )
    wanted = None if currencies is None else set(currencies)
    inserted: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    with db_transaction(conn):
        for code, rate in table.rates:
            if code == base_currency or (wanted is not None and code not in wanted):
                continue
            bucket = _store_rate(conn, table.effective_date, code, base_currency, rate)
            {"inserted": inserted, "updated": updated, "unchanged": unchanged}[bucket].append(code)
    return RefreshResult(table.effective_date, tuple(inserted), tuple(updated), tuple(unchanged))


def has_rate_on(conn: sqlite3.Connection, base_currency: str, on_date: dt.date) -> bool:
    """True when any cached rate into ``base_currency`` is dated exactly ``on_date``."""
    return fx_repo.any_rate_on(conn, on_date, base_currency)


def list_recent_rates(conn: sqlite3.Connection, *, limit: int = 50) -> list[FxRate]:
    """Most recent cached rates, newest first."""
    return fx_repo.list_recent(conn, limit=limit)


__all__ = [
    "FxConverter",
    "FxUnavailableError",
    "HasBaseCurrency",
    "RateSeries",
    "RefreshResult",
    "build_converter",
    "converter_for",
    "currency_by_account",
    "has_rate_on",
    "list_recent_rates",
    "refresh_from_source",
    "txn_base_of",
]
