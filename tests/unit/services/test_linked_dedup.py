"""T-FIX4: linked planned rows suppress their recurring occurrence everywhere (ADR-0087)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.repositories import accounts, categories, planned, recurring
from budget_planner.services import (
    account_planned as ap,
    budget as bs,
    forecast as fc,
    recurring as recurring_svc,
)

USER_ID = 1
TODAY = date(2026, 11, 6)
OCC = date(2026, 11, 15)
START = date(2026, 11, 1)
END = date(2026, 12, 1)
AMOUNT = 1000


@pytest.fixture
def ids(conn: sqlite3.Connection) -> dict[str, int]:
    acct = accounts.create(
        conn, USER_ID, NewAccount(name="A", currency="PLN", opening_balance=100_000)
    )
    cat = categories.create(conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE))
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 7, 15),
            category_id=cat.id,
            account_id=acct.id,
            default_amount=AMOUNT,
            day_of_month=15,
        ),
    )
    recurring.set_next_due(conn, USER_ID, rule.id, next_due=OCC, last_promoted_date=None)
    return {"acct": acct.id, "cat": cat.id, "rule": rule.id}


def _planned(
    conn: sqlite3.Connection, ids: dict[str, int], on: date, *, linked: bool, amount: int = AMOUNT
) -> None:
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=on,
            category_id=ids["cat"],
            account_id=ids["acct"],
            amount=amount,
            recurring_rule_id=ids["rule"] if linked else None,
            occurrence_date=OCC if linked else None,
        ),
    )


def _budget(conn: sqlite3.Connection) -> int:
    return bs.committed_in_window(conn, USER_ID, start=START, end=END)


def _forecast(conn: sqlite3.Connection, ids: dict[str, int]) -> int:
    events = fc._collect_events(conn, USER_ID, TODAY, END, {ids["cat"]: Direction.EXPENSE})
    return sum(ev.amount_minor for evs in events.values() for ev in evs)


def _accounts(conn: sqlite3.Connection) -> int:
    window = ap.PlannedWindow(start=START, end=END)
    return sum(ap.planned_net_by_account(conn, USER_ID, window).values())


def test_linked_row_in_window_counted_once_everywhere(
    conn: sqlite3.Connection, ids: dict[str, int]
) -> None:
    _planned(conn, ids, OCC, linked=True)

    assert _budget(conn) == AMOUNT
    assert _forecast(conn, ids) == -AMOUNT
    assert _accounts(conn) == -AMOUNT


def test_linked_row_moved_outside_window_still_suppresses(
    conn: sqlite3.Connection, ids: dict[str, int]
) -> None:
    _planned(conn, ids, date(2027, 3, 1), linked=True)

    assert _budget(conn) == 0
    assert _accounts(conn) == 0
    assert _forecast(conn, ids) == 0


def test_unlinked_row_same_day_does_not_suppress(
    conn: sqlite3.Connection, ids: dict[str, int]
) -> None:
    _planned(conn, ids, OCC, linked=False, amount=300)

    assert _budget(conn) == AMOUNT + 300
    assert _forecast(conn, ids) == -(AMOUNT + 300)
    assert _accounts(conn) == -(AMOUNT + 300)


def test_linked_occurrence_keys_ignores_unlinked(
    conn: sqlite3.Connection, ids: dict[str, int]
) -> None:
    _planned(conn, ids, OCC, linked=False)
    assert recurring_svc.linked_occurrence_keys(conn, USER_ID) == frozenset()

    _planned(conn, ids, OCC, linked=True)
    assert recurring_svc.linked_occurrence_keys(conn, USER_ID) == frozenset({(ids["rule"], OCC)})
