from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from budget_planner.domain.fx import NewFxRate
from budget_planner.repositories import audit, fx


def test_upsert_and_find(conn: sqlite3.Connection) -> None:
    rate = fx.upsert_rate(
        conn,
        NewFxRate(
            date=date(2026, 1, 15),
            from_ccy="EUR",
            to_ccy="PLN",
            rate=Decimal("4.3123"),
        ),
    )
    assert rate.rate == Decimal("4.3123")
    assert fx.find_rate(conn, date(2026, 1, 15), "EUR", "PLN") == rate
    assert fx.find_rate(conn, date(2026, 1, 16), "EUR", "PLN") is None
    ops = [e.operation.value for e in audit.list_entries(conn, None, "fx_rate", rate.id)]
    assert ops == ["create"]


def test_upsert_updates_existing(conn: sqlite3.Connection) -> None:
    original = fx.upsert_rate(
        conn,
        NewFxRate(
            date=date(2026, 1, 15),
            from_ccy="EUR",
            to_ccy="PLN",
            rate=Decimal("4.3"),
        ),
    )
    updated = fx.upsert_rate(
        conn,
        NewFxRate(
            date=date(2026, 1, 15),
            from_ccy="EUR",
            to_ccy="PLN",
            rate=Decimal("4.35"),
        ),
    )
    assert updated.id == original.id
    assert updated.rate == Decimal("4.35")
    ops = [e.operation.value for e in audit.list_entries(conn, None, "fx_rate", updated.id)]
    assert ops == ["create", "update"]


def test_latest_rate(conn: sqlite3.Connection) -> None:
    fx.upsert_rate(
        conn,
        NewFxRate(
            date=date(2026, 1, 1),
            from_ccy="EUR",
            to_ccy="PLN",
            rate=Decimal("4.30"),
        ),
    )
    newer = fx.upsert_rate(
        conn,
        NewFxRate(
            date=date(2026, 2, 1),
            from_ccy="EUR",
            to_ccy="PLN",
            rate=Decimal("4.35"),
        ),
    )
    assert fx.latest_rate(conn, "EUR", "PLN") == newer
    assert fx.latest_rate(conn, "USD", "PLN") is None
