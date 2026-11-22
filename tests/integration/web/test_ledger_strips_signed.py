"""T-Q209 — Ledger planned and recurring strips net by direction (ADR-0008, Q-010)."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
)
from tests.ui_map import _html, ledger

USER_ID = 1


def _seed(settings: Settings) -> None:
    conn = get_connection(settings)
    try:
        acc = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
        )
        inc = categories_repo.create(
            conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
        )
        exp = categories_repo.create(
            conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
        )
        soon = clock.today_local(Settings()) + timedelta(days=5)
        for cat, amount in ((inc, 500000), (exp, 120050)):
            planned_repo.create(
                conn,
                USER_ID,
                NewPlannedTransaction(
                    operation_date=soon,
                    category_id=cat.id,
                    account_id=acc.id,
                    amount=amount,
                    description="p",
                ),
            )
            recurring_repo.create_rule(
                conn,
                USER_ID,
                NewRecurringRule(
                    cadence=Cadence.MONTHLY,
                    start_date=date(2026, 1, 1),
                    category_id=cat.id,
                    account_id=acc.id,
                    default_amount=amount,
                    default_description="r",
                ),
            )
    finally:
        conn.close()


def test_planned_strip_is_signed_net(client: TestClient, _migrated: Settings) -> None:
    _seed(_migrated)
    html = client.get("/ledger?view=planned").text
    assert _html.text_of(html, ledger.planned_strip).startswith("2 items · 3,799.50 PLN")


def test_recurring_strip_splits_in_and_out(client: TestClient, _migrated: Settings) -> None:
    _seed(_migrated)
    html = client.get("/ledger?view=recurring").text
    text = _html.text_of(html, ledger.recurring_strip)
    assert "Monthly out 1,200.50 PLN" in text
    assert "Monthly in 5,000.00 PLN" in text
