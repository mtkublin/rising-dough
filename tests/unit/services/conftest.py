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
#
# ``world_with_two_users`` seeds users 1 (the owner) and 2 (the other) with disjoint, fully deterministic data, and
# ``world_with_tombstones`` adds soft-deleted and inactive rows to the OWNER only. Every money-service test that needs
# "user 2 and dead rows must never leak into user 1's numbers" builds on these two fixtures (T-Q221, Q-015). To extend:
# add the new row to ``_seed_user`` (and an id to ``OwnedRows``) or to ``world_with_tombstones`` (and ``Tombstones``),
# keep every amount a pure function of the user id, and never read the clock: ids and dates are pinned below.

import datetime as _dt  # noqa: E402
from dataclasses import dataclass  # noqa: E402

from budget_planner.domain.accounts import NewAccount  # noqa: E402
from budget_planner.domain.budgets import NewBudgetDefault  # noqa: E402
from budget_planner.domain.categories import NewCategory  # noqa: E402
from budget_planner.domain.enums import Cadence, Direction  # noqa: E402
from budget_planner.domain.planned import NewPlannedTransaction  # noqa: E402
from budget_planner.domain.recurring import (  # noqa: E402
    AmountFormula,
    FormulaTerm,
    NewRecurringRule,
    PatchRecurringRule,
    RecurringRule,
)
from budget_planner.domain.transactions import NewTransaction  # noqa: E402
from budget_planner.repositories import (  # noqa: E402
    accounts as _accounts_repo,
    budgets as _budgets_repo,
    categories as _categories_repo,
    planned as _planned_repo,
    recurring as _recurring_repo,
    transactions as _transactions_repo,
)
from budget_planner.services import preferences as _preferences_svc  # noqa: E402

WORLD_DAY = _dt.date(2026, 11, 10)  # the day of each user's transaction
WORLD_TODAY = _dt.date(2026, 11, 12)  # the "today" every money-service case injects
EXPENSE_RULE_DUE = _dt.date(2026, 11, 15)  # next_due of each user's monthly expense rule
INCOME_RULE_DUE = _dt.date(
    2026, 12, 1
)  # next_due of each user's monthly income rule (the income anchor)
OWNER_ID = 1
OTHER_ID = 2
OWNER_BALANCE = 123_456
OTHER_BALANCE = 777
TOMBSTONE_TXN_AMOUNT = 4_242
TOMBSTONE_ACCOUNT_BALANCE = 9_999
TOMBSTONE_PLANNED_AMOUNT = 8_000
INACTIVE_RULE_AMOUNT = 6_000
DELETED_RULE_AMOUNT = 7_000


def txn_amount(user_id: int) -> int:
    """Amount of the user's expense transaction on ``WORLD_DAY``."""
    return 1_000 * user_id


def planned_amount(user_id: int) -> int:
    """Amount of the user's unpromoted planned expense on ``WORLD_DAY + 3``."""
    return 500 * user_id


def expense_rule_amount(user_id: int) -> int:
    """Default amount of the user's monthly expense rule (next_due ``EXPENSE_RULE_DUE``)."""
    return 700 * user_id


def income_rule_amount(user_id: int) -> int:
    """Default amount of the user's monthly income rule (next_due ``INCOME_RULE_DUE``)."""
    return 5_000 * user_id


def budget_amount(user_id: int) -> int:
    """Default monthly budget of the user's expense category."""
    return 3_000 * user_id


@dataclass(frozen=True)
class OwnedRows:
    """Ids of one user's rows in the shared test world."""

    user_id: int
    account_id: int
    category_id: int  # expense category (carries the budget default)
    transaction_id: int
    planned_id: int
    income_category_id: int  # the user's income anchor
    rule_id: int  # monthly expense rule
    income_rule_id: int  # monthly income rule


@dataclass(frozen=True)
class Tombstones:
    """Soft-deleted / inactive rows added to the OWNER by ``world_with_tombstones``."""

    account_id: int  # soft-deleted account
    category_id: int  # soft-deleted (archived) category
    transaction_id: int  # soft-deleted transaction on the live account and category
    planned_id: int  # soft-deleted planned row on the live account and category
    inactive_rule_id: int  # active=0 rule on the live account and category
    deleted_rule_id: int  # soft-deleted rule on the live account and category


@dataclass(frozen=True)
class World:
    """Two users with disjoint data; ``owner`` carries ``OWNER_BALANCE``, ``other`` carries ``OTHER_BALANCE``.

    ``tombstones`` is ``None`` unless the world was built by ``world_with_tombstones``.
    """

    owner: OwnedRows
    other: OwnedRows
    tombstones: Tombstones | None = None


def seed_rule(
    conn: sqlite3.Connection,
    user_id: int,
    category_id: int,
    account_id: int,
    due: _dt.date,
    *,
    amount: int,
    active: bool = True,
) -> RecurringRule:
    """A monthly rule starting (and due) on ``due``; ``next_due`` is pinned so the real clock never leaks in."""
    rule = _recurring_repo.create_rule(
        conn,
        user_id,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=due,
            category_id=category_id,
            account_id=account_id,
            default_amount=amount,
            default_description=f"rule-{user_id}-{amount}",
            active=active,
        ),
    )
    _recurring_repo.set_next_due(conn, user_id, rule.id, next_due=due, last_promoted_date=None)
    return rule


def seed_formula_rule(
    conn: sqlite3.Connection, user_id: int, rows: OwnedRows, *, due: _dt.date
) -> RecurringRule:
    """A monthly expense rule on a fresh category whose amount is 10% of ``rows.category_id``'s monthly rules.

    Live source rules only: with the world's 700u rule that is ``70u`` in November (inactive and deleted tombstone
    rules on the same category must not count).
    """
    category = _categories_repo.create(
        conn, user_id, NewCategory(name=f"cat-formula-{user_id}", direction=Direction.EXPENSE)
    )
    rule = seed_rule(conn, user_id, category.id, rows.account_id, due, amount=1)
    return _recurring_repo.update_rule(
        conn,
        user_id,
        rule.id,
        PatchRecurringRule(
            amount_formula=AmountFormula(
                terms=(
                    FormulaTerm(
                        sign="+", coefficient_bps=1_000, source_category_ids=(rows.category_id,)
                    ),
                )
            )
        ),
    )


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
    income = _categories_repo.create(
        conn, user_id, NewCategory(name=f"inc-{user_id}", direction=Direction.INCOME)
    )
    txn = _transactions_repo.create(
        conn,
        user_id,
        NewTransaction(
            operation_date=WORLD_DAY,
            category_id=category.id,
            account_id=account.id,
            amount=txn_amount(user_id),
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
            amount=planned_amount(user_id),
            description=f"planned-{user_id}",
        ),
    )
    rule = seed_rule(
        conn,
        user_id,
        category.id,
        account.id,
        EXPENSE_RULE_DUE,
        amount=expense_rule_amount(user_id),
    )
    income_rule = seed_rule(
        conn, user_id, income.id, account.id, INCOME_RULE_DUE, amount=income_rule_amount(user_id)
    )
    _budgets_repo.set_default(
        conn, user_id, NewBudgetDefault(category_id=category.id, amount=budget_amount(user_id))
    )
    _preferences_svc.set_income_anchor_category_id(conn, user_id, income.id)
    return OwnedRows(
        user_id, account.id, category.id, txn.id, planned.id, income.id, rule.id, income_rule.id
    )


@pytest.fixture
def world_with_two_users(conn: sqlite3.Connection) -> World:
    """User 1 and user 2 each own an account, two categories, a transaction, a planned row, two rules and a budget."""
    conn.execute("DELETE FROM transactions")
    conn.execute("DELETE FROM planned_transactions")
    owner = _seed_user(conn, OWNER_ID, OWNER_BALANCE)
    other = _seed_user(conn, OTHER_ID, OTHER_BALANCE)
    return World(owner, other)


@pytest.fixture
def world_with_tombstones(conn: sqlite3.Connection, world_with_two_users: World) -> World:
    """The two-user world plus soft-deleted and inactive rows for the owner (see ``Tombstones``)."""
    owner = world_with_two_users.owner
    dead_account = _accounts_repo.create(
        conn,
        OWNER_ID,
        NewAccount(name="dead-account", currency="PLN", opening_balance=TOMBSTONE_ACCOUNT_BALANCE),
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
            account_id=owner.account_id,
            amount=TOMBSTONE_TXN_AMOUNT,
            description="dead-txn",
        ),
    )
    dead_planned = _planned_repo.create(
        conn,
        OWNER_ID,
        NewPlannedTransaction(
            operation_date=WORLD_DAY + _dt.timedelta(days=3),
            category_id=owner.category_id,
            account_id=owner.account_id,
            amount=TOMBSTONE_PLANNED_AMOUNT,
            description="dead-planned",
        ),
    )
    inactive_rule = seed_rule(
        conn,
        OWNER_ID,
        owner.category_id,
        owner.account_id,
        EXPENSE_RULE_DUE,
        amount=INACTIVE_RULE_AMOUNT,
        active=False,
    )
    deleted_rule = seed_rule(
        conn,
        OWNER_ID,
        owner.category_id,
        owner.account_id,
        EXPENSE_RULE_DUE,
        amount=DELETED_RULE_AMOUNT,
    )
    _recurring_repo.soft_delete_rule(conn, OWNER_ID, deleted_rule.id)
    _planned_repo.soft_delete(conn, OWNER_ID, dead_planned.id)
    _transactions_repo.soft_delete(conn, OWNER_ID, dead_txn.id)
    _categories_repo.soft_delete(conn, OWNER_ID, dead_category.id)
    _accounts_repo.soft_delete(conn, OWNER_ID, dead_account.id)
    return World(
        owner,
        world_with_two_users.other,
        Tombstones(
            account_id=dead_account.id,
            category_id=dead_category.id,
            transaction_id=dead_txn.id,
            planned_id=dead_planned.id,
            inactive_rule_id=inactive_rule.id,
            deleted_rule_id=deleted_rule.id,
        ),
    )
