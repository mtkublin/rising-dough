"""Mutation-kill tests for ``services/preferences`` (T-Q247, ADR-0131).

Pins the exact error and log text (operators grep for it) and per-user scoping of the income anchor.
Complements ``test_preferences.py``.
"""

from __future__ import annotations

import logging
import sqlite3

import pytest

from budget_planner.domain.enums import Direction
from budget_planner.domain.preferences import PREF_INCOME_ANCHOR_CATEGORY_ID
from budget_planner.repositories import (
    categories as categories_repo,
    preferences as preferences_repo,
)
from budget_planner.services import preferences as preferences_svc
from tests.unit.services.conftest import OTHER_ID, OWNER_ID, World

LOGGER = "budget_planner.services.preferences"


def _records(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == LOGGER and r.levelno == level]


def test_corrupt_value_logs_value_and_user_and_returns_none(
    conn: sqlite3.Connection, world_with_two_users: World, caplog: pytest.LogCaptureFixture
) -> None:
    preferences_repo.upsert(conn, OWNER_ID, PREF_INCOME_ANCHOR_CATEGORY_ID, "not-an-int")
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        assert preferences_svc.get_income_anchor_category_id(conn, OWNER_ID) is None
    assert _records(caplog, logging.WARNING) == [
        "corrupt income_anchor_category_id value='not-an-int' (user_id=1)"
    ]
    # the other user's anchor is untouched by the corrupt owner row
    assert (
        preferences_svc.get_income_anchor_category_id(conn, OTHER_ID)
        == world_with_two_users.other.income_category_id
    )


def test_set_rejects_missing_category_with_exact_message(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    other_cat = world_with_two_users.other.income_category_id  # another user's category
    with pytest.raises(preferences_svc.InvalidAnchorCategoryError) as err:
        preferences_svc.set_income_anchor_category_id(conn, OWNER_ID, other_cat)
    assert str(err.value) == f"category {other_cat} not found or soft-deleted"


def test_set_rejects_expense_category_with_exact_message(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    expense = world_with_two_users.owner.category_id
    with pytest.raises(preferences_svc.InvalidAnchorCategoryError) as err:
        preferences_svc.set_income_anchor_category_id(conn, OWNER_ID, expense)
    assert str(err.value) == (
        f"category {expense} direction=expense; income anchor requires direction=income"
    )
    transit = categories_repo.find_by_name(conn, OWNER_ID, "Transit")
    assert transit is not None
    with pytest.raises(preferences_svc.InvalidAnchorCategoryError) as err2:
        preferences_svc.set_income_anchor_category_id(conn, OWNER_ID, transit.id)
    assert str(err2.value) == (
        f"category {transit.id} direction={transit.direction.value}; "
        "income anchor requires direction=income"
    )


def test_resolve_logs_soft_deleted_anchor(
    conn: sqlite3.Connection, world_with_two_users: World, caplog: pytest.LogCaptureFixture
) -> None:
    anchor = world_with_two_users.owner.income_category_id
    categories_repo.soft_delete(conn, OWNER_ID, anchor)
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        assert preferences_svc.resolve_income_anchor_category(conn, OWNER_ID) is None
    assert _records(caplog, logging.DEBUG) == [
        f"income anchor category_id={anchor} resolves to None (soft-deleted or missing)"
    ]
    resolved_other = preferences_svc.resolve_income_anchor_category(conn, OTHER_ID)
    assert resolved_other is not None
    assert resolved_other.id == world_with_two_users.other.income_category_id


def test_resolve_logs_flipped_direction(
    conn: sqlite3.Connection, world_with_two_users: World, caplog: pytest.LogCaptureFixture
) -> None:
    anchor = world_with_two_users.owner.income_category_id
    conn.execute(
        "UPDATE categories SET direction = ? WHERE id = ?", (Direction.EXPENSE.value, anchor)
    )
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        assert preferences_svc.resolve_income_anchor_category(conn, OWNER_ID) is None
    assert _records(caplog, logging.DEBUG) == [
        f"income anchor category_id={anchor} direction=expense (expected income)"
    ]


def test_resolve_returns_live_anchor_without_logging(
    conn: sqlite3.Connection, world_with_two_users: World, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        category = preferences_svc.resolve_income_anchor_category(conn, OWNER_ID)
    assert category is not None
    assert (category.id, category.name) == (world_with_two_users.owner.income_category_id, "inc-1")
    assert _records(caplog, logging.DEBUG) == []
