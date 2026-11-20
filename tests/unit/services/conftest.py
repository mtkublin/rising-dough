# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""Shared fixtures for service-layer unit tests (temp DB + schema + seeds)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from tests.db_template import sqlite_url


@pytest.fixture
def conn(migrated_db: Path) -> Iterator[sqlite3.Connection]:
    settings = Settings(_env_file=None, database_url=sqlite_url(migrated_db))
    c = get_connection(settings)
    try:
        yield c
    finally:
        c.close()


# --- S3 (ADR-0130): two-user and tombstone worlds for the user-isolation registry ---------------------------------

import datetime as _dt  # noqa: E402
from dataclasses import dataclass  # noqa: E402

from budget_planner.domain.accounts import NewAccount  # noqa: E402
from budget_planner.domain.categories import NewCategory  # noqa: E402
from budget_planner.domain.enums import Direction  # noqa: E402
from budget_planner.domain.planned import NewPlannedTransaction  # noqa: E402
from budget_planner.domain.transactions import NewTransaction  # noqa: E402
from budget_planner.repositories import (  # noqa: E402
    accounts as _accounts_repo,
    categories as _categories_repo,
    planned as _planned_repo,
    transactions as _transactions_repo,
)

WORLD_DAY = _dt.date(2026, 11, 10)
OWNER_ID = 1
OTHER_ID = 2
OWNER_BALANCE = 123_456
OTHER_BALANCE = 777


@dataclass(frozen=True)
class OwnedRows:
    """Ids of one user's rows in the shared test world."""

    user_id: int
    account_id: int
    category_id: int
    transaction_id: int
    planned_id: int


@dataclass(frozen=True)
class World:
    """Two users with disjoint data; ``owner`` carries ``OWNER_BALANCE``, ``other`` carries ``OTHER_BALANCE``."""

    owner: OwnedRows
    other: OwnedRows


def _seed_user(conn: sqlite3.Connection, user_id: int, balance: int) -> OwnedRows:
    if not conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone():
        conn.execute(
            "INSERT INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?)",
            (user_id, f"user{user_id}", f"user{user_id}@example.test", "x"),
        )
    account = _accounts_repo.create(
        conn, user_id, NewAccount(name=f"acct-{user_id}", currency="PLN", opening_balance=balance)
    )
    category = _categories_repo.create(
        conn, user_id, NewCategory(name=f"cat-{user_id}", direction=Direction.EXPENSE)
    )
    txn = _transactions_repo.create(
        conn,
        user_id,
        NewTransaction(
            operation_date=WORLD_DAY,
            category_id=category.id,
            account_id=account.id,
            amount=1_000 * user_id,
            description=f"txn-{user_id}",
        ),
    )
    planned = _planned_repo.create(
        conn,
        user_id,
        NewPlannedTransaction(
            operation_date=WORLD_DAY + _dt.timedelta(days=3),
            category_id=category.id,
            account_id=account.id,
            amount=500 * user_id,
            description=f"planned-{user_id}",
        ),
    )
    return OwnedRows(user_id, account.id, category.id, txn.id, planned.id)


@pytest.fixture
def world_with_two_users(conn: sqlite3.Connection) -> World:
    """User 1 and user 2 each own an account, category, transaction and planned row (disjoint ids)."""
    conn.execute("DELETE FROM transactions")
    conn.execute("DELETE FROM planned_transactions")
    owner = _seed_user(conn, OWNER_ID, OWNER_BALANCE)
    other = _seed_user(conn, OTHER_ID, OTHER_BALANCE)
    return World(owner, other)


@pytest.fixture
def world_with_tombstones(conn: sqlite3.Connection, world_with_two_users: World) -> World:
    """The two-user world plus a soft-deleted account, category and transaction for the owner."""
    owner = world_with_two_users.owner
    dead_account = _accounts_repo.create(
        conn, OWNER_ID, NewAccount(name="dead-account", currency="PLN", opening_balance=9_999)
    )
    dead_category = _categories_repo.create(
        conn, OWNER_ID, NewCategory(name="dead-category", direction=Direction.EXPENSE)
    )
    dead_txn = _transactions_repo.create(
        conn,
        OWNER_ID,
        NewTransaction(
            operation_date=WORLD_DAY,
            category_id=owner.category_id,
            account_id=dead_account.id,
            amount=4_242,
            description="dead-txn",
        ),
    )
    stamp = "2026-11-01T00:00:00.000Z"
    for table, row_id in (
        ("transactions", dead_txn.id),
        ("categories", dead_category.id),
        ("accounts", dead_account.id),
    ):
        conn.execute(f"UPDATE {table} SET deleted_at = ? WHERE id = ?", (stamp, row_id))  # noqa: S608
    return world_with_two_users
