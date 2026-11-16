"""Unit tests for :mod:`services.categories` archive/restore (T-R44, ADR-0056 §6)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.domain.system_categories import RECONCILIATION_CATEGORY_NAME
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    recurring as recurring_repo,
)
from budget_planner.services import categories as categories_svc

USER_ID = 1


@pytest.fixture
def groc_id(conn: sqlite3.Connection) -> int:
    return categories_repo.create(
        conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    ).id


def test_archive_ok(conn: sqlite3.Connection, groc_id: int) -> None:
    archived = categories_svc.archive(conn, USER_ID, groc_id)
    assert archived.deleted_at is not None


def test_archive_missing_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(categories_svc.CategoryNotFoundError):
        categories_svc.archive(conn, USER_ID, 99_999)


def test_archive_already_archived_raises(conn: sqlite3.Connection, groc_id: int) -> None:
    categories_svc.archive(conn, USER_ID, groc_id)
    with pytest.raises(categories_svc.CategoryNotFoundError):
        categories_svc.archive(conn, USER_ID, groc_id)


def test_archive_system_raises(conn: sqlite3.Connection) -> None:
    recon = categories_repo.find_by_name(conn, USER_ID, RECONCILIATION_CATEGORY_NAME)
    assert recon is not None
    with pytest.raises(categories_svc.SystemCategoryError):
        categories_svc.archive(conn, USER_ID, recon.id)


def test_archive_warn_mode_logs_and_proceeds(conn: sqlite3.Connection, groc_id: int) -> None:
    acc = accounts_repo.create(
        conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
    )
    recurring_repo.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 1),
            category_id=groc_id,
            account_id=acc.id,
            default_amount=1_000,
            default_description="",
        ),
    )
    # Warn mode is the default — the archive succeeds despite the live rule.
    archived = categories_svc.archive(conn, USER_ID, groc_id)
    assert archived.deleted_at is not None


def test_archive_block_mode_rejects_when_live_rules(conn: sqlite3.Connection, groc_id: int) -> None:
    acc = accounts_repo.create(
        conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
    )
    recurring_repo.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 1),
            category_id=groc_id,
            account_id=acc.id,
            default_amount=1_000,
            default_description="",
        ),
    )
    with pytest.raises(categories_svc.CategoryHasLiveRulesError):
        categories_svc.archive(conn, USER_ID, groc_id, block_on_live_rules=True)


def test_restore_ok(conn: sqlite3.Connection, groc_id: int) -> None:
    categories_svc.archive(conn, USER_ID, groc_id)
    restored = categories_svc.restore(conn, USER_ID, groc_id)
    assert restored.deleted_at is None


def test_restore_non_archived_raises(conn: sqlite3.Connection, groc_id: int) -> None:
    with pytest.raises(categories_svc.CategoryNotFoundError):
        categories_svc.restore(conn, USER_ID, groc_id)


def test_restore_missing_raises(conn: sqlite3.Connection) -> None:
    with pytest.raises(categories_svc.CategoryNotFoundError):
        categories_svc.restore(conn, USER_ID, 99_999)
