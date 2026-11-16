"""Tests for the fortune aggregation service (T-083, ADR-0024)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.config import Settings
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import accounts, categories, transactions
from budget_planner.services import fortune

USER_ID = 1


def _settings(base: str = "PLN") -> Settings:
    return Settings(_env_file=None, base_currency=base)


def _mk_expense(conn: sqlite3.Connection, *, account_id: int, cat_id: int, amount: int) -> None:
    transactions.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 1, 5),
            category_id=cat_id,
            account_id=account_id,
            amount=amount,
        ),
    )


@pytest.fixture
def cats(conn: sqlite3.Connection) -> dict[str, int]:
    expense = categories.create(
        conn, USER_ID, NewCategory(name="Food", direction=Direction.EXPENSE)
    )
    return {"expense": expense.id}


def test_asset_only_no_liabilities(conn: sqlite3.Connection) -> None:
    accounts.create(conn, USER_ID, NewAccount(name="Bank", currency="PLN", opening_balance=100_000))
    totals = fortune.compute_fortune(conn, USER_ID, _settings())
    assert totals.assets_by_ccy == {"PLN": 100_000}
    assert totals.liabilities_by_ccy == {}
    assert totals.net_by_ccy == {"PLN": 100_000}
    assert totals.assets_base == 100_000
    assert totals.liabilities_base == 0
    assert totals.net_base == 100_000


def test_liability_only(conn: sqlite3.Connection, cats: dict[str, int]) -> None:
    visa = accounts.create(
        conn,
        USER_ID,
        NewAccount(
            name="Visa",
            currency="PLN",
            is_liability=True,
            credit_limit_minor=1_000_000,
        ),
    )
    _mk_expense(conn, account_id=visa.id, cat_id=cats["expense"], amount=50_000)
    totals = fortune.compute_fortune(conn, USER_ID, _settings())
    assert totals.assets_by_ccy == {}
    assert totals.liabilities_by_ccy == {"PLN": 50_000}
    assert totals.net_by_ccy == {"PLN": -50_000}
    assert totals.assets_base == 0
    assert totals.liabilities_base == 50_000
    assert totals.net_base == -50_000


def test_mixed_single_currency(conn: sqlite3.Connection, cats: dict[str, int]) -> None:
    accounts.create(conn, USER_ID, NewAccount(name="Bank", currency="PLN", opening_balance=100_000))
    visa = accounts.create(
        conn,
        USER_ID,
        NewAccount(name="Visa", currency="PLN", is_liability=True, credit_limit_minor=1_000_000),
    )
    _mk_expense(conn, account_id=visa.id, cat_id=cats["expense"], amount=20_000)
    totals = fortune.compute_fortune(conn, USER_ID, _settings())
    assert totals.assets_base == 100_000
    assert totals.liabilities_base == 20_000
    assert totals.net_base == 80_000


def test_multi_currency_buckets(conn: sqlite3.Connection) -> None:
    accounts.create(
        conn, USER_ID, NewAccount(name="PLN Bank", currency="PLN", opening_balance=100_000)
    )
    accounts.create(
        conn, USER_ID, NewAccount(name="EUR Bank", currency="EUR", opening_balance=50_000)
    )
    totals = fortune.compute_fortune(conn, USER_ID, _settings(base="PLN"))
    assert totals.assets_by_ccy == {"PLN": 100_000, "EUR": 50_000}
    assert totals.net_by_ccy == {"PLN": 100_000, "EUR": 50_000}
    # base selection only picks PLN
    assert totals.assets_base == 100_000
    assert totals.net_base == 100_000


def test_soft_deleted_account_excluded(conn: sqlite3.Connection) -> None:
    a = accounts.create(
        conn, USER_ID, NewAccount(name="Bank", currency="PLN", opening_balance=100_000)
    )
    accounts.create(conn, USER_ID, NewAccount(name="Other", currency="PLN", opening_balance=25_000))
    accounts.soft_delete(conn, USER_ID, a.id)
    totals = fortune.compute_fortune(conn, USER_ID, _settings())
    assert totals.assets_base == 25_000


@pytest.mark.parametrize(
    ("asset", "liability_balance"),
    [
        (100_000, -20_000),
        (0, -5_000),
        (500_000, 0),
        (-10_000, -1_000),
        (1_000_000, -1_000_000),
    ],
)
def test_invariant_net_eq_assets_minus_liabilities(
    conn: sqlite3.Connection,
    cats: dict[str, int],
    asset: int,
    liability_balance: int,
) -> None:
    accounts.create(conn, USER_ID, NewAccount(name="Bank", currency="PLN", opening_balance=asset))
    visa = accounts.create(
        conn,
        USER_ID,
        NewAccount(name="Visa", currency="PLN", is_liability=True, credit_limit_minor=1_000_000),
    )
    if liability_balance != 0:
        _mk_expense(conn, account_id=visa.id, cat_id=cats["expense"], amount=abs(liability_balance))
    totals = fortune.compute_fortune(conn, USER_ID, _settings())
    assert totals.net_base == totals.assets_base - totals.liabilities_base


def test_over_limit_balance_included(conn: sqlite3.Connection, cats: dict[str, int]) -> None:
    visa = accounts.create(
        conn,
        USER_ID,
        NewAccount(name="Visa", currency="PLN", is_liability=True, credit_limit_minor=100_000),
    )
    _mk_expense(conn, account_id=visa.id, cat_id=cats["expense"], amount=250_000)
    totals = fortune.compute_fortune(conn, USER_ID, _settings())
    assert totals.liabilities_by_ccy["PLN"] == 250_000
    assert totals.net_by_ccy["PLN"] == -250_000


def test_zero_balance_account_counted_as_zero(conn: sqlite3.Connection) -> None:
    accounts.create(conn, USER_ID, NewAccount(name="Empty", currency="PLN", opening_balance=0))
    totals = fortune.compute_fortune(conn, USER_ID, _settings())
    assert totals.assets_by_ccy == {"PLN": 0}
    assert totals.net_by_ccy == {"PLN": 0}
    assert totals.assets_base == 0
    assert totals.liabilities_base == 0
    assert totals.net_base == 0
