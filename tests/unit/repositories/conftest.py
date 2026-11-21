"""Shared fixtures: temp DB connection with all migrations + seeds applied."""

from __future__ import annotations

import sqlite3

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import accounts, categories

USER_ID = 1


@pytest.fixture
def account_id(conn: sqlite3.Connection) -> int:
    return accounts.create(conn, USER_ID, NewAccount(name="ING", currency="PLN")).id


@pytest.fixture
def dest_account_id(conn: sqlite3.Connection) -> int:
    return accounts.create(conn, USER_ID, NewAccount(name="Savings", currency="PLN")).id


@pytest.fixture
def category_id(conn: sqlite3.Connection) -> int:
    return categories.create(
        conn, USER_ID, NewCategory(name="Food", direction=Direction.EXPENSE)
    ).id


@pytest.fixture
def income_category_id(conn: sqlite3.Connection) -> int:
    return categories.create(
        conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    ).id
