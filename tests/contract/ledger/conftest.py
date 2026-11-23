# ruff: noqa: F811  (pytest fixtures re-exported then used as parameters)
"""Fixtures for the ledger-surface contract tests (T-UT04c).

Re-uses the web-integration client stack (temp DB, session cookie, CSRF-aware
client) so contract tests never touch the production database.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)
from budget_planner.web.app import create_app
from tests.contract.ledger.support import USER_ID
from tests.integration.web.conftest import (  # noqa: F401  (fixtures re-exported)
    _migrated,
    anon_client,
    client,
    session_cookie,
    settings,
)


@pytest.fixture
def raw_client(_migrated: Settings, session_cookie: tuple[str, str]) -> Iterator[TestClient]:
    """Signed-in client with NO automatic CSRF header (for CSRF enforcement)."""
    app = create_app(settings=_migrated)
    with TestClient(app, base_url="https://testserver") as c:
        c.cookies.set(*session_cookie)
        yield c


@pytest.fixture
def seeded(_migrated: Settings) -> dict[str, int]:
    """Two accounts, expense/income/transit categories, 1 txn, 1 planned, 1 rule."""
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(conn, USER_ID, NewAccount(name="Main", currency="PLN"))
        acc2 = accounts_repo.create(conn, USER_ID, NewAccount(name="Savings", currency="PLN"))
        exp = categories_repo.create(
            conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
        )
        inc = categories_repo.create(
            conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
        )
        move = categories_repo.create(
            conn, USER_ID, NewCategory(name="Move", direction=Direction.TRANSIT)
        )
        today = clock.today_local(_migrated)
        txn = transactions_repo.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=today - timedelta(days=3),
                category_id=exp.id,
                account_id=acc.id,
                amount=1500,
                description="seed txn",
            ),
        )
        pl = planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=today + timedelta(days=5),
                category_id=exp.id,
                account_id=acc.id,
                amount=2500,
                description="seed planned",
            ),
        )
        rule = recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=today - timedelta(days=40),
                category_id=exp.id,
                account_id=acc.id,
                default_amount=50000,
                default_description="seed rule",
            ),
        )
        return {
            "acc": acc.id,
            "acc2": acc2.id,
            "exp": exp.id,
            "inc": inc.id,
            "move": move.id,
            "txn": txn.id,
            "pl": pl.id,
            "rule": rule.id,
        }
    finally:
        conn.close()
