"""Tests for the balance service (T-021)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import accounts, categories, transactions
from budget_planner.services import balance
from budget_planner.services.balance import AccountNotFoundError, SignedLeg

USER_ID = 1


# ---------------------------------------------------------------------------
# fixtures: a mini world with every direction
# ---------------------------------------------------------------------------
@pytest.fixture
def ids(conn: sqlite3.Connection) -> dict[str, int]:
    checking = accounts.create(
        conn, USER_ID, NewAccount(name="Checking", currency="PLN", opening_balance=100_000)
    )
    savings = accounts.create(conn, USER_ID, NewAccount(name="Savings", currency="PLN"))
    eur = accounts.create(
        conn, USER_ID, NewAccount(name="EUR Cash", currency="EUR", opening_balance=50_000)
    )
    income_cat = categories.create(
        conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    )
    expense_cat = categories.create(
        conn, USER_ID, NewCategory(name="Food", direction=Direction.EXPENSE)
    )
    transit_cat = categories.find_by_name(conn, USER_ID, "Transit")
    adjustment_cat = categories.find_by_name(conn, USER_ID, "Reconciliation")
    assert transit_cat is not None and adjustment_cat is not None
    return {
        "checking": checking.id,
        "savings": savings.id,
        "eur": eur.id,
        "income_cat": income_cat.id,
        "expense_cat": expense_cat.id,
        "transit_cat": transit_cat.id,
        "adjustment_cat": adjustment_cat.id,
    }


def _mk_txn(
    conn: sqlite3.Connection,
    *,
    on: date,
    cat: int,
    account: int,
    amount: int,
    dest: int | None = None,
) -> int:
    return transactions.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=on,
            category_id=cat,
            account_id=account,
            dest_account_id=dest,
            amount=amount,
        ),
    ).id


# ---------------------------------------------------------------------------
# signed_legs — pure
# ---------------------------------------------------------------------------
def test_signed_legs_income(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    txn_id = _mk_txn(
        conn, on=date(2026, 1, 5), cat=ids["income_cat"], account=ids["checking"], amount=50_000
    )
    txn = transactions.find_by_id(conn, USER_ID, txn_id)
    assert txn is not None
    legs = balance.signed_legs(txn, Direction.INCOME)
    assert legs == (SignedLeg(account_id=ids["checking"], amount_minor=50_000),)


def test_signed_legs_expense(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    txn_id = _mk_txn(
        conn, on=date(2026, 1, 10), cat=ids["expense_cat"], account=ids["checking"], amount=20_000
    )
    txn = transactions.find_by_id(conn, USER_ID, txn_id)
    assert txn is not None
    legs = balance.signed_legs(txn, Direction.EXPENSE)
    assert legs == (SignedLeg(account_id=ids["checking"], amount_minor=-20_000),)


def test_signed_legs_transit_two_legs(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    txn_id = _mk_txn(
        conn,
        on=date(2026, 1, 15),
        cat=ids["transit_cat"],
        account=ids["checking"],
        amount=30_000,
        dest=ids["savings"],
    )
    txn = transactions.find_by_id(conn, USER_ID, txn_id)
    assert txn is not None
    legs = balance.signed_legs(txn, Direction.TRANSIT)
    assert set(legs) == {
        SignedLeg(account_id=ids["checking"], amount_minor=-30_000),
        SignedLeg(account_id=ids["savings"], amount_minor=30_000),
    }


def test_signed_legs_adjustment_passes_through(
    conn: sqlite3.Connection, ids: dict[str, int]
) -> None:
    # Create via reconciliation seed category directly.
    txn_id = _mk_txn(
        conn, on=date(2026, 2, 1), cat=ids["adjustment_cat"], account=ids["checking"], amount=-5000
    )
    txn = transactions.find_by_id(conn, USER_ID, txn_id)
    assert txn is not None
    legs = balance.signed_legs(txn, Direction.ADJUSTMENT)
    assert legs == (SignedLeg(account_id=ids["checking"], amount_minor=-5000),)


# ---------------------------------------------------------------------------
# derive_balance
# ---------------------------------------------------------------------------
def test_opening_only(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    assert balance.derive_balance(conn, USER_ID, ids["savings"]) == 0
    assert balance.derive_balance(conn, USER_ID, ids["checking"]) == 100_000


def test_income_adds(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    _mk_txn(
        conn, on=date(2026, 1, 5), cat=ids["income_cat"], account=ids["checking"], amount=50_000
    )
    assert balance.derive_balance(conn, USER_ID, ids["checking"]) == 150_000


def test_expense_subtracts(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    _mk_txn(
        conn, on=date(2026, 1, 10), cat=ids["expense_cat"], account=ids["checking"], amount=20_000
    )
    assert balance.derive_balance(conn, USER_ID, ids["checking"]) == 80_000


def test_transit_moves_funds(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    _mk_txn(
        conn,
        on=date(2026, 1, 15),
        cat=ids["transit_cat"],
        account=ids["checking"],
        amount=30_000,
        dest=ids["savings"],
    )
    assert balance.derive_balance(conn, USER_ID, ids["checking"]) == 70_000
    assert balance.derive_balance(conn, USER_ID, ids["savings"]) == 30_000


def test_adjustment_signed_pass_through(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    _mk_txn(
        conn, on=date(2026, 2, 1), cat=ids["adjustment_cat"], account=ids["checking"], amount=-5000
    )
    assert balance.derive_balance(conn, USER_ID, ids["checking"]) == 95_000


def test_as_of_date_inclusive(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    _mk_txn(
        conn, on=date(2026, 1, 5), cat=ids["income_cat"], account=ids["checking"], amount=50_000
    )
    _mk_txn(
        conn, on=date(2026, 1, 10), cat=ids["expense_cat"], account=ids["checking"], amount=20_000
    )
    _mk_txn(
        conn,
        on=date(2026, 1, 15),
        cat=ids["transit_cat"],
        account=ids["checking"],
        amount=30_000,
        dest=ids["savings"],
    )
    # as_of 2026-01-10 includes income + expense but not transit
    assert (
        balance.derive_balance(conn, USER_ID, ids["checking"], as_of_date=date(2026, 1, 10))
        == 130_000
    )


def test_soft_deleted_excluded(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    txn_id = _mk_txn(
        conn, on=date(2026, 1, 5), cat=ids["income_cat"], account=ids["checking"], amount=50_000
    )
    assert balance.derive_balance(conn, USER_ID, ids["checking"]) == 150_000
    transactions.soft_delete(conn, USER_ID, txn_id)
    assert balance.derive_balance(conn, USER_ID, ids["checking"]) == 100_000


def test_cross_account_isolation(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    _mk_txn(
        conn, on=date(2026, 1, 5), cat=ids["income_cat"], account=ids["checking"], amount=50_000
    )
    assert balance.derive_balance(conn, USER_ID, ids["eur"]) == 50_000  # unchanged


def test_unknown_account_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(AccountNotFoundError):
        balance.derive_balance(conn, USER_ID, 9999)


# ---------------------------------------------------------------------------
# account_stats
# ---------------------------------------------------------------------------
def test_account_stats_empty(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    stats = balance.account_stats(conn, USER_ID, ids["savings"])
    assert stats.balance == 0
    assert stats.txn_count == 0
    assert stats.last_txn_date is None
    assert stats.avg_inflow_minor == 0
    assert stats.avg_outflow_minor == 0


def test_account_stats_mixed(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    _mk_txn(
        conn, on=date(2026, 1, 5), cat=ids["income_cat"], account=ids["checking"], amount=40_000
    )
    _mk_txn(
        conn, on=date(2026, 1, 7), cat=ids["income_cat"], account=ids["checking"], amount=60_000
    )
    _mk_txn(
        conn, on=date(2026, 1, 10), cat=ids["expense_cat"], account=ids["checking"], amount=20_000
    )
    _mk_txn(
        conn,
        on=date(2026, 1, 15),
        cat=ids["transit_cat"],
        account=ids["checking"],
        amount=30_000,
        dest=ids["savings"],
    )
    _mk_txn(
        conn,
        on=date(2026, 2, 1),
        cat=ids["adjustment_cat"],
        account=ids["checking"],
        amount=-5000,
    )
    stats = balance.account_stats(conn, USER_ID, ids["checking"])
    assert stats.txn_count == 5  # all legs touching checking
    assert stats.avg_inflow_minor == 50_000  # (40_000 + 60_000) / 2
    assert stats.avg_outflow_minor == 20_000  # single expense of 20_000
    assert stats.last_txn_date == "2026-02-01"
    assert stats.balance == 100_000 + 40_000 + 60_000 - 20_000 - 30_000 - 5000


def test_account_stats_transit_dest_counts(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    _mk_txn(
        conn,
        on=date(2026, 1, 15),
        cat=ids["transit_cat"],
        account=ids["checking"],
        amount=30_000,
        dest=ids["savings"],
    )
    stats = balance.account_stats(conn, USER_ID, ids["savings"])
    assert stats.txn_count == 1
    assert stats.last_txn_date == "2026-01-15"
    assert stats.balance == 30_000


def test_account_stats_unknown_account(conn: sqlite3.Connection) -> None:
    with pytest.raises(AccountNotFoundError):
        balance.account_stats(conn, USER_ID, 404)


def test_account_stats_last_activity_date_property(
    conn: sqlite3.Connection, ids: dict[str, int]
) -> None:
    stats_empty = balance.account_stats(conn, USER_ID, ids["savings"])
    assert stats_empty.last_activity_date is None
    _mk_txn(conn, on=date(2026, 3, 7), cat=ids["income_cat"], account=ids["savings"], amount=1)
    stats = balance.account_stats(conn, USER_ID, ids["savings"])
    assert stats.last_activity_date == date(2026, 3, 7)
