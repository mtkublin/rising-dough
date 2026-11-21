"""Shared fixtures + helpers for the plan-surface contract tests (T-UT04d, ADR-0106 section 1).

No tests live here; ``test_plan_budget.py`` and ``test_plan_views.py`` import
from it. Fixtures come from the web-integration conftest so the contract
tests run against the same CSRF-aware, authenticated client and temp DB.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Mapping

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import accounts as accounts_repo, categories as categories_repo
from budget_planner.web.app import create_app
from tests.integration.web.conftest import (
    _migrated,
    anon_client,
    client,
    session_cookie,
    settings,
)

USER_ID = 1

# Non-autouse fixtures re-exported from the web-integration conftest. The autouse
# ``_fast_bcrypt`` is deliberately not re-exported: as a plugin it would go session-wide.
__all__ = ["_migrated", "anon_client", "client", "session_cookie", "settings"]


@pytest.fixture
def raw_client(_migrated: Settings, session_cookie: tuple[str, str]) -> Iterator[TestClient]:
    """Signed in, but no CSRF priming and no auto-attached token."""
    with TestClient(create_app(settings=_migrated), base_url="https://testserver") as c:
        c.cookies.set(*session_cookie)
        yield c


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def cat_id(db: sqlite3.Connection) -> int:
    return categories_repo.create(
        db, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    ).id


@pytest.fixture
def income_cat_id(db: sqlite3.Connection) -> int:
    return categories_repo.create(
        db, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    ).id


@pytest.fixture
def account_id(db: sqlite3.Connection) -> int:
    return accounts_repo.create(
        db, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=100_000)
    ).id


def audit_count(db: sqlite3.Connection, entity_type: str) -> int:
    row = db.execute(
        "SELECT COUNT(*) FROM audit_log WHERE entity_type = ? AND user_id = ? "
        "AND actor_user_id = ?",
        (entity_type, USER_ID, USER_ID),
    ).fetchone()
    return int(row[0])


def audit_total(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0])


def hx_events(headers: Mapping[str, str]) -> dict[str, object]:
    events: dict[str, object] = json.loads(headers.get("HX-Trigger", "{}"))
    return events
