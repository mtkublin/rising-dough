"""T-Q209 — Ledger planned and recurring strips net by direction (ADR-0008, Q-010)."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    fx as fx_repo,
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
    text = _html.text_of(client.get("/ledger?view=planned").text, ledger.planned_strip)
    assert text.startswith("2 items · 3,799.50 PLN")


def test_recurring_strip_splits_in_and_out(client: TestClient, _migrated: Settings) -> None:
    _seed(_migrated)
    text = _html.text_of(client.get("/ledger?view=recurring").text, ledger.recurring_strip)
    assert "Monthly out 1,200.50 PLN" in text
    assert "Monthly in 5,000.00 PLN" in text


# ---------------------------------------------------------------------------
# T-Q215: strips convert across currencies (ADR-0006, ADR-0139)
# ---------------------------------------------------------------------------


def _seed_eur_rule(settings: Settings, *, rate: str | None) -> None:
    conn = get_connection(settings)
    try:
        eur = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Euro", currency="EUR", opening_balance=0)
        )
        exp = categories_repo.create(
            conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
        )
        recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=date(2026, 1, 1),
                category_id=exp.id,
                account_id=eur.id,
                default_amount=10000,
                default_description="r",
            ),
        )
        planned_repo.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=clock.today_local(Settings()) + timedelta(days=5),
                category_id=exp.id,
                account_id=eur.id,
                amount=2000,
                description="p",
            ),
        )
        if rate is not None:
            fx_repo.upsert_rate(
                conn,
                NewFxRate(date=date(2026, 1, 1), from_ccy="EUR", to_ccy="PLN", rate=Decimal(rate)),
            )
    finally:
        conn.close()


def test_recurring_strip_converts_eur_rule_to_pln(client: TestClient, _migrated: Settings) -> None:
    _seed_eur_rule(_migrated, rate="4.30")
    text = _html.text_of(client.get("/ledger?view=recurring").text, ledger.recurring_strip)
    assert "Monthly out 430.00 PLN" in text


def test_planned_strip_converts_eur_row_to_pln(client: TestClient, _migrated: Settings) -> None:
    _seed_eur_rule(_migrated, rate="4.30")
    text = _html.text_of(client.get("/ledger?view=planned").text, ledger.planned_strip)
    assert text.startswith("1 items · -86.00 PLN")


def test_strips_503_when_rate_missing(client: TestClient, _migrated: Settings) -> None:
    _seed_eur_rule(_migrated, rate=None)
    assert client.get("/ledger?view=recurring").status_code == 503
    assert client.get("/ledger?view=planned").status_code == 503
