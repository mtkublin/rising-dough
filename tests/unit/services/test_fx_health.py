"""FX freshness decision (T-Q292, ADR-0146): exact verdicts and the all-users read."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.fx import NewFxRate
from budget_planner.repositories import accounts, fx as fx_repo
from budget_planner.services import fx_health

TODAY = date(2026, 11, 23)
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def _eval(used: list[tuple[str, date | None]]) -> fx_health.FxHealth:
    return fx_health.evaluate(used, today=TODAY, max_age_days=4, now=NOW)


def test_ok_at_the_age_limit() -> None:
    v = _eval([("USD", date(2026, 11, 19)), ("EUR", TODAY)])
    assert (v.ok, v.status) == (True, "ok")
    assert v.body() == {
        "status": "ok",
        "currencies": [
            {"code": "EUR", "newest_date": "2026-11-23", "age_days": 0},
            {"code": "USD", "newest_date": "2026-11-19", "age_days": 4},
        ],
        "max_age_days": 4,
        "checked_at": "2026-11-23T12:00:00+00:00",
    }


def test_stale_lists_the_ages() -> None:
    v = _eval([("USD", date(2026, 11, 18)), ("EUR", TODAY)])
    assert (v.ok, v.status) == (False, "stale")
    assert [(c.code, c.age_days) for c in v.currencies] == [("EUR", 0), ("USD", 5)]


def test_never_wins_over_stale() -> None:
    v = _eval([("USD", date(2026, 1, 1)), ("CHF", None)])
    assert (v.ok, v.status) == (False, "never")
    assert v.body()["currencies"] == [
        {"code": "CHF", "newest_date": None, "age_days": None},
        {"code": "USD", "newest_date": "2026-01-01", "age_days": 326},
    ]


def test_future_dated_rate_counts_as_age_zero() -> None:
    assert _eval([("USD", date(2026, 11, 25))]).currencies[0].age_days == 0


def test_no_foreign_currency_is_ok_with_refresh_active() -> None:
    v = _eval([])
    assert (v.ok, v.status, v.currencies) == (True, "ok", ())


def _rate(conn: sqlite3.Connection, ccy: str, day: date) -> None:
    fx_repo.upsert_rate(conn, NewFxRate(date=day, from_ccy=ccy, to_ccy="PLN", rate=Decimal("4.2")))


def _user2(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO users(id, name) VALUES (2, 'other')")


def _check(
    conn: sqlite3.Connection, *, active: bool = True, required: bool = False
) -> fx_health.FxHealth:
    return fx_health.check(
        conn,
        base_currency="PLN",
        refresh_active=active,
        refresh_required=required,
        today=TODAY,
        max_age_days=4,
        now=NOW,
    )


def test_check_counts_second_users_live_foreign_account_and_ignores_deleted(
    conn: sqlite3.Connection,
) -> None:
    accounts.create(conn, 1, NewAccount(name="PLN", currency="PLN"))
    _user2(conn)
    accounts.create(conn, 2, NewAccount(name="Euro", currency="EUR"))
    gone = accounts.create(conn, 1, NewAccount(name="Old", currency="GBP"))
    accounts.soft_delete(conn, 1, gone.id)
    _rate(conn, "EUR", date(2026, 11, 10))
    _rate(conn, "GBP", date(2026, 11, 23))
    before = conn.total_changes
    v = _check(conn)
    assert (v.ok, v.status) == (False, "stale")
    assert [(c.code, c.newest_date, c.age_days) for c in v.currencies] == [
        ("EUR", date(2026, 11, 10), 13)
    ]
    assert conn.total_changes == before  # read-only
    _rate(conn, "EUR", date(2026, 11, 22))
    assert _check(conn).status == "ok"


def test_check_never_and_disabled(conn: sqlite3.Connection) -> None:
    _user2(conn)
    accounts.create(conn, 2, NewAccount(name="Dollar", currency="USD"))
    assert _check(conn).status == "never"
    off = _check(conn, active=False)
    assert (off.ok, off.status) == (True, "disabled")
    required_off = _check(conn, active=False, required=True)
    assert (required_off.ok, required_off.status) == (False, "disabled")
