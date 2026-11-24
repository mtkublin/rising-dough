"""Forecast summary delta and horizon months (T-UR34j, ADR-0147 §3, ADR-0148, gap G9)."""

from __future__ import annotations

import sqlite3
from datetime import date

from budget_planner.config import Settings
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
)
from budget_planner.services import forecast as fc
from tests.unit.services.conftest import OTHER_ID, OWNER_ID

TODAY = date(2026, 10, 23)
OPENING = 1_000_000


def _user_world(conn: sqlite3.Connection, user_id: int) -> tuple[int, int, int]:
    if user_id != OWNER_ID:
        conn.execute(
            "INSERT INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?)",
            (user_id, f"user{user_id}", f"user{user_id}@example.test", "x"),
        )
    acct = accounts_repo.create(
        conn, user_id, NewAccount(name=f"a-{user_id}", currency="PLN", opening_balance=OPENING)
    ).id
    inc = categories_repo.create(
        conn, user_id, NewCategory(name=f"inc-{user_id}", direction=Direction.INCOME)
    ).id
    exp = categories_repo.create(
        conn, user_id, NewCategory(name=f"exp-{user_id}", direction=Direction.EXPENSE)
    ).id
    return acct, inc, exp


def _plan(
    conn: sqlite3.Connection, user_id: int, on: date, cat: int, acct: int, *, amt: int
) -> None:
    planned_repo.create(
        conn,
        user_id,
        NewPlannedTransaction(operation_date=on, category_id=cat, account_id=acct, amount=amt),
    )


def _summary(
    conn: sqlite3.Connection, months: int, user_id: int = OWNER_ID
) -> fc.ProjectionSummary:
    projection = fc.monthly_projection(conn, user_id, Settings(_env_file=None), TODAY, months)
    summary = fc.projection_summary(projection, now_value=OPENING)
    assert summary is not None
    return summary


def test_increasing_projection_delta_is_positive_magnitude_with_up(
    conn: sqlite3.Connection,
) -> None:
    acct, inc, _ = _user_world(conn, OWNER_ID)
    _plan(conn, OWNER_ID, date(2026, 11, 5), inc, acct, amt=4_210)
    s = _summary(conn, 6)
    assert (s.now_value, s.end_point.end_balance_minor) == (OPENING, OPENING + 4_210)
    assert (s.delta_minor, s.delta_direction, s.months) == (4_210, fc.TrendDirection.UP, 6)


def test_decreasing_projection_delta_is_magnitude_with_down(conn: sqlite3.Connection) -> None:
    acct, _, exp = _user_world(conn, OWNER_ID)
    _plan(conn, OWNER_ID, date(2026, 12, 5), exp, acct, amt=1_500)
    s = _summary(conn, 3)
    assert s.end_point.end_balance_minor == OPENING - 1_500
    assert (s.delta_minor, s.delta_direction, s.months) == (1_500, fc.TrendDirection.DOWN, 3)


def test_flat_projection_delta_is_zero_with_flat(conn: sqlite3.Connection) -> None:
    _user_world(conn, OWNER_ID)
    s = _summary(conn, 12)
    assert (s.now_value, s.end_point.end_balance_minor) == (OPENING, OPENING)
    assert (s.delta_minor, s.delta_direction, s.months) == (0, fc.TrendDirection.FLAT, 12)


def test_other_users_planned_rows_do_not_change_the_delta(conn: sqlite3.Connection) -> None:
    acct, inc, _ = _user_world(conn, OWNER_ID)
    other_acct, other_inc, _ = _user_world(conn, OTHER_ID)
    _plan(conn, OWNER_ID, date(2026, 11, 5), inc, acct, amt=700)
    _plan(conn, OTHER_ID, date(2026, 11, 6), other_inc, other_acct, amt=99_999)
    s = _summary(conn, 6)
    assert (s.delta_minor, s.delta_direction) == (700, fc.TrendDirection.UP)


def test_single_month_projection_is_flat_with_one_month() -> None:
    point = fc.MonthlyProjectionPoint(
        month=date(2026, 10, 1), label="Oct 2026", end_balance_minor=5
    )
    s = fc.projection_summary((point,), now_value=5)
    assert s is not None
    assert (s.delta_minor, s.delta_direction, s.months) == (0, fc.TrendDirection.FLAT, 1)


def test_delta_runs_from_todays_net_worth_not_first_month_end() -> None:
    pts = tuple(
        fc.MonthlyProjectionPoint(month=date(2026, m, 1), label=str(m), end_balance_minor=v)
        for m, v in ((11, 900), (12, 1_200))
    )
    up = fc.projection_summary(pts, now_value=1_000)
    assert up is not None
    assert (up.now_value, up.delta_minor, up.delta_direction) == (1_000, 200, fc.TrendDirection.UP)
    down = fc.projection_summary(pts, now_value=1_500)
    assert down is not None
    assert (down.delta_minor, down.delta_direction) == (300, fc.TrendDirection.DOWN)
    flat = fc.projection_summary(pts, now_value=1_200)
    assert flat is not None
    assert (flat.delta_minor, flat.delta_direction) == (0, fc.TrendDirection.FLAT)
