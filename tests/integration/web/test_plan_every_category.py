"""Plan · budget and Plan · year: budgeted categories are rows, every other live expense category
sits in the collapsed "N categories without a budget" list (T-UR75, T-UR80, operator R14, R20).

A category with no budget is listed with or without ledger records; one archived before the
shown month is not (ADR-0136); another user's categories never appear.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    budgets as budgets_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from tests.auth_support import seed_login_user
from tests.contract.test_plan_support import USER_ID
from tests.ui_map import _html, plan_budget, plan_year

pytest_plugins = ("tests.contract.test_plan_support",)

BUDGET = "/plan?tab=budget&year=2026&month=3"
YEAR = "/plan?tab=year&year=2026"
LATE_BUDGET = "/plan?tab=budget&year=2099&month=1"
LATE_YEAR = "/plan?tab=year&year=2099"


@pytest.fixture
def world(db: sqlite3.Connection, account_id: int) -> None:
    """Budgeted (default 500.00); no budget: Shop (spent 40.00), Unused; Old (archived this
    month, so still listed in 2026 and gone from 2099); Other (second user's)."""
    budgeted = categories_repo.create(
        db, USER_ID, NewCategory(name="Budgeted", direction=Direction.EXPENSE)
    )
    budgets_repo.set_default(db, USER_ID, NewBudgetDefault(category_id=budgeted.id, amount=50_000))
    shop = categories_repo.create(
        db, USER_ID, NewCategory(name="Shop", direction=Direction.EXPENSE)
    )
    categories_repo.create(db, USER_ID, NewCategory(name="Unused", direction=Direction.EXPENSE))
    transactions_repo.create(
        db,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 3, 10),
            category_id=shop.id,
            account_id=account_id,
            amount=4_000,
            description="shop",
        ),
    )
    old = categories_repo.create(db, USER_ID, NewCategory(name="Old", direction=Direction.EXPENSE))
    categories_repo.soft_delete(db, USER_ID, old.id)
    seed_login_user(db, user_id=2, email="other@example.com")
    categories_repo.create(db, 2, NewCategory(name="Other", direction=Direction.EXPENSE))
    db.commit()


def test_budget_splits_budgeted_rows_from_the_collapsed_list(
    client: TestClient, world: None
) -> None:
    page = client.get(BUDGET).text

    assert _html.count(page, plan_budget.row("Budgeted")) == 1
    assert _html.count(page, plan_budget.row("Shop")) == 0
    assert _html.count(page, plan_budget.row("Unused")) == 0
    assert _html.text_of(page, plan_budget.disclosure) == "3 categories without a budget"
    assert _html.count(page, plan_budget.unbudgeted_rows) == 3


def test_budget_list_rows_show_values_and_set_budget_in_the_status_cell(
    client: TestClient, world: None
) -> None:
    page = client.get(BUDGET).text

    shop = _html.texts(page, plan_budget.unbudgeted_cells("Shop"))
    unused = _html.texts(page, plan_budget.unbudgeted_cells("Unused"))
    # name, bar, "<spent> / <budget>", status with the set-budget button, menu cell.
    assert shop == ["Shop", "░" * 10, "40.00 / —", "no budget set budget", ""]
    assert unused == ["Unused", "░" * 10, "0.00 / —", "no budget set budget", ""]
    assert _html.texts(page, plan_budget.set_budget_button("Unused")) == ["set budget"]
    assert _html.count(page, plan_budget.unbudgeted_status_cell("Shop")) == 1
    assert _html.count(page, plan_budget.edit_budget_item("Unused")) == 0
    button = _html.resolve_one(page, plan_budget.set_budget_button("Unused"))
    assert str(button["hx-get"]).endswith("/overrides/new?year=2026&month=3&tier=default")


def test_budget_omits_archived_before_the_month_and_other_users(
    client: TestClient, world: None
) -> None:
    page = client.get(LATE_BUDGET).text

    assert _html.text_of(page, plan_budget.disclosure) == "2 categories without a budget"
    assert _html.count(page, plan_budget.unbudgeted_row("Old")) == 0
    assert _html.count(page, plan_budget.unbudgeted_row("Other")) == 0
    assert _html.count(page, plan_budget.row("Other")) == 0


def test_year_has_budgeted_rows_and_lists_the_rest_in_the_disclosure(
    client: TestClient, world: None
) -> None:
    page = client.get(YEAR).text

    assert _html.count(page, plan_year.row("Budgeted")) == 1
    assert _html.count(page, plan_year.row("Shop")) == 0
    assert _html.count(page, plan_year.row("Unused")) == 0
    assert _html.text_of(page, plan_year.disclosure) == "3 categories without a budget"
    assert _html.texts(page, plan_year.unbudgeted("Shop")) == ["Shop"]
    assert _html.texts(page, plan_year.unbudgeted("Unused")) == ["Unused"]
    assert _html.count(page, plan_year.unbudgeted("Other")) == 0


def test_year_omits_archived_before_the_year_and_other_users(
    client: TestClient, world: None
) -> None:
    page = client.get(LATE_YEAR).text

    assert _html.text_of(page, plan_year.disclosure) == "2 categories without a budget"
    assert _html.count(page, plan_year.unbudgeted("Old")) == 0
    assert _html.count(page, plan_year.unbudgeted("Other")) == 0
