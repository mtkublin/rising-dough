"""Shared fixtures: temp DB connection with all migrations + seeds applied."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import accounts, categories

USER_ID = 1


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    url = f"sqlite:///{(tmp_path / 'db.sqlite').as_posix()}"
    settings = Settings(_env_file=None, database_url=url)
    c = get_connection(settings)
    apply_migrations(c)
    try:
        yield c
    finally:
        c.close()


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
