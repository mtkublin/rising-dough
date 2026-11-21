"""T-Q210: ``validate_transit_shape`` rule and service-level reconcile guard."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import Account, NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import accounts, categories
from budget_planner.services import reconciliation
from budget_planner.services.transactions import (
    ValidationError,
    check_transit_shape,
    validate_transit_shape,
)

USER_ID = 1


def _acct(conn: sqlite3.Connection, name: str, currency: str = "PLN") -> Account:
    return accounts.create(
        conn, USER_ID, NewAccount(name=name, currency=currency, opening_balance=1000)
    )


def test_transit_needs_destination(conn: sqlite3.Connection) -> None:
    a = _acct(conn, "A")
    with pytest.raises(ValidationError, match="requires a destination"):
        validate_transit_shape(Direction.TRANSIT, a, None)


def test_transit_rejects_same_account_and_cross_currency(conn: sqlite3.Connection) -> None:
    a, e = _acct(conn, "A"), _acct(conn, "E", "EUR")
    with pytest.raises(ValidationError, match="differ"):
        validate_transit_shape(Direction.TRANSIT, a, a)
    with pytest.raises(ValidationError, match="cross-currency"):
        validate_transit_shape(Direction.TRANSIT, a, e)


def test_transit_valid_and_other_directions_unconstrained(conn: sqlite3.Connection) -> None:
    a, b = _acct(conn, "A"), _acct(conn, "B")
    validate_transit_shape(Direction.TRANSIT, a, b)
    validate_transit_shape(Direction.EXPENSE, a, None)


def test_check_unknown_destination(conn: sqlite3.Connection) -> None:
    a = _acct(conn, "A")
    with pytest.raises(ValidationError, match="unknown destination"):
        check_transit_shape(
            conn, USER_ID, direction=Direction.TRANSIT, account_id=a.id, dest_account_id=9999
        )


def test_reconcile_with_transit_category_stores_nothing(conn: sqlite3.Connection) -> None:
    a = _acct(conn, "A")
    tr = categories.create(conn, USER_ID, NewCategory(name="Move", direction=Direction.TRANSIT))
    with pytest.raises(ValidationError, match="requires a destination"):
        reconciliation.reconcile(conn, USER_ID, a.id, 5000, date(2026, 11, 21), category_id=tr.id)
    assert conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 0
