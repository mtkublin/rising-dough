"""FxConverter, refresh path and live client factory (T-Q212, ADR-0139)."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from budget_planner.config import Settings
from budget_planner.domain.fx import NewFxRate
from budget_planner.repositories import fx as fx_repo
from budget_planner.services import fx as fx_service
from budget_planner.services.fx import FxUnavailableError

DAY = date(2026, 2, 1)


def _put(conn: sqlite3.Connection, on: date, rate: str, ccy: str = "EUR") -> None:
    fx_repo.upsert_rate(conn, NewFxRate(date=on, from_ccy=ccy, to_ccy="PLN", rate=Decimal(rate)))


def _converter(conn: sqlite3.Connection) -> fx_service.FxConverter:
    return fx_service.converter_for(conn, Settings(_env_file=None), DAY)


def test_identity_needs_no_rate(conn: sqlite3.Connection) -> None:
    assert _converter(conn).to_base(12_345, "PLN") == 12_345


def test_exact_date_then_latest_on_or_before(conn: sqlite3.Connection) -> None:
    _put(conn, date(2026, 1, 15), "4.28")
    _put(conn, DAY, "4.40")
    _put(conn, date(2026, 2, 20), "9.99")
    fx = _converter(conn)
    assert fx.rate_for("EUR", DAY) == Decimal("4.40")
    assert fx.rate_for("EUR", date(2026, 1, 20)) == Decimal("4.28")
    assert fx.rate_for("EUR") == Decimal("4.40")  # reference day, never the future row


def test_missing_rate_raises_never_rate_one(conn: sqlite3.Connection) -> None:
    fx = _converter(conn)
    with pytest.raises(FxUnavailableError, match="EUR->PLN"):
        fx.to_base(100, "EUR")
    _put(conn, date(2026, 3, 1), "4")  # only a later rate cached
    with pytest.raises(FxUnavailableError):
        _converter(conn).to_base(100, "EUR", DAY)


def test_rounds_half_even_and_preserves_sign(conn: sqlite3.Connection) -> None:
    _put(conn, DAY, "0.5")
    fx = _converter(conn)
    assert fx.to_base(5, "EUR") == 2  # 0.025 PLN -> 2.5 grosz -> half even
    assert fx.to_base(7, "EUR") == 4  # 3.5 -> 4
    assert fx.to_base(-7, "EUR") == -4


def test_zero_decimal_currency(conn: sqlite3.Connection) -> None:
    _put(conn, DAY, "0.0275", "JPY")
    assert _converter(conn).to_base(10_000, "JPY") == 27_500


@pytest.mark.parametrize("bad", ["0", "-1", "NaN", "Infinity"])
def test_new_rate_rejects_non_positive_or_non_finite(bad: str) -> None:
    with pytest.raises(ValueError, match="fx rate"):
        NewFxRate(date=DAY, from_ccy="EUR", to_ccy="PLN", rate=Decimal(bad))
