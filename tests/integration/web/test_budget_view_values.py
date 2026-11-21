"""T-Q237 (Q-039): budget numbers on Today, Plan and Budget equal the service values."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from datetime import date
from typing import Any, cast

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from budget_planner import clock
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
    summary = budget_service.month_summary(db, USER_ID, year, month, today=today)
    view = view_models.budget_view(summary, today)
    expected_per_day = _money_num(client, view_models.left_per_day(summary))

    soup = _soup(client.get("/today").text)

    hero_amount = soup.select_one(".rd-hero__amount span")
    assert hero_amount is not None
    assert hero_amount.get_text(strip=True) == expected_per_day
    assert view.spent_pct == 25
    spent_bar = soup.select_one(".rd-progress__spent")
    assert spent_bar is not None
    assert re.search(r"width: 25(\.0)?%", str(spent_bar.get("style")))
    assert f"day {view.period_day} of {view.period_total_days}" in soup.get_text(" ", strip=True)


def test_plan_budget_tab_shows_view_model_values(
    client: TestClient,
    db: sqlite3.Connection,
    today: date,
    world: None,
) -> None:
    picked = budget_service.resolve_picker_month(db, USER_ID, today)
    summary = budget_service.month_summary_for_picker(db, USER_ID, picked, today)
    view = view_models.budget_view(summary, today)

    soup = _soup(client.get("/plan?tab=budget").text)

    perday = soup.select_one(".rd-period-bar__perday")
    assert perday is not None
    assert perday.get_text(strip=True) == _money_num(client, view.left_per_day_minor)
    row = soup.select_one("tr[id^=budget-row-]")
    assert row is not None
    cells = [c.get_text(strip=True) for c in row.select("td")]
    assert cells[1] == _money_num(client, BUDGET_MINOR)
    assert cells[2] == _money_num(client, SPENT_MINOR)
    assert cells[4] == _money_num(client, BUDGET_MINOR - SPENT_MINOR)
    used = row.select_one(".rd-progress__spent")
    assert used is not None
    assert re.search(r"width: 25(\.0)?%", str(used.get("style")))


def test_budget_page_row_bar_uses_view_percent(client: TestClient, world: None) -> None:
    soup = _soup(client.get("/budget").text)

    bar = soup.select_one(".remainder-bar")
    assert bar is not None
    assert bar.get("aria-valuenow") == "25"


def test_budget_view_percent_clamps_and_flags_over() -> None:
    assert view_models.clamped_percent(150, 100) == 100
    assert view_models.clamped_percent(-5, 100) == 0
    assert view_models.clamped_percent(5, 0) == 0
