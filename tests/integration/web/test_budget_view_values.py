"""T-Q237 (Q-039): budget numbers on Today, Plan and Budget equal the service values."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date
from typing import Any, cast

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.clock import DEFAULT_DISPLAY_TIMEZONE
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from budget_planner.services import budget as budget_service
from budget_planner.web import view_models
from tests.ui_map import _html, plan, today as today_ui

USER_ID = 1
BUDGET_MINOR = 100_000
SPENT_MINOR = 25_000
CCY = "PLN"


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def today(_migrated: Settings) -> date:
    return clock.today_local(_migrated)


@pytest.fixture
def world(db: sqlite3.Connection, today: date) -> None:
    account = accounts_repo.create(
        db, USER_ID, NewAccount(name="Checking", currency=CCY, opening_balance=500_000)
    )
    groceries = categories_repo.create(
        db, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    )
    budgets_repo.set_default(
        db, USER_ID, NewBudgetDefault(category_id=groceries.id, amount=BUDGET_MINOR)
    )
    transactions_repo.create(
        db,
        USER_ID,
        NewTransaction(
            operation_date=today,
            category_id=groceries.id,
            account_id=account.id,
            amount=SPENT_MINOR,
        ),
    )


def _money_num(client: TestClient, minor: int) -> str:
    env = cast(Any, client.app).state.jinja_env
    result: str = env.filters["money_num"](minor, CCY)
    return result


def _soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def test_today_hero_shows_view_model_values(
    client: TestClient,
    db: sqlite3.Connection,
    _migrated: Settings,
    today: date,
    world: None,
) -> None:
    year, month = budget_service.fiscal_month_for(db, USER_ID, today)
    summary = budget_service.month_summary(
        db,
        USER_ID,
        year,
        month,
        today=today,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    view = view_models.budget_view(summary, today)
    expected_per_day = _money_num(client, view_models.left_per_day(summary))

    html = client.get("/today").text

    assert _html.text_of(html, today_ui.hero_per_day) == expected_per_day
    assert view.spent_pct == 25
    spent_bar = _html.resolve_one(html, today_ui.spent_bar)
    assert float(str(spent_bar["aria-valuenow"])) == 25
    assert f"day {view.period_day} of {view.period_total_days}" in _html.page_text(html)


def test_plan_budget_tab_shows_view_model_values(
    client: TestClient,
    db: sqlite3.Connection,
    today: date,
    world: None,
) -> None:
    picked = budget_service.resolve_picker_month(db, USER_ID, today)
    summary = budget_service.month_summary_for_picker(
        db,
        USER_ID,
        picked,
        today,
        base_currency="PLN",
        display_timezone=DEFAULT_DISPLAY_TIMEZONE,
    )
    view = view_models.budget_view(summary, today)

    html = client.get("/plan?tab=budget").text

    assert _html.text_of(html, plan.period_per_day) == _money_num(client, view.left_per_day_minor)
    cells = _html.texts(html, plan.budget_row_cells)
    assert cells[1] == _money_num(client, BUDGET_MINOR)
    assert cells[2] == _money_num(client, SPENT_MINOR)
    assert cells[4] == _money_num(client, BUDGET_MINOR - SPENT_MINOR)
    used = _html.resolve_one(html, plan.budget_row_spent)
    assert float(str(used["aria-valuenow"])) == 25


def test_budget_page_row_bar_uses_view_percent(client: TestClient, world: None) -> None:
    html = client.get("/budget").text

    bar = _html.resolve_one(html, plan.remainder_bar)
    assert bar.get("aria-valuenow") == "25"


def test_budget_view_percent_clamps_and_flags_over() -> None:
    assert view_models.clamped_percent(150, 100) == 100
    assert view_models.clamped_percent(-5, 100) == 0
    assert view_models.clamped_percent(5, 0) == 0
