"""Plan · budget and Plan · year list every live expense category (T-UR75, operator R14).

A category with no ledger record and no budget is still a row; one archived before the shown
month is not (ADR-0136); another user's categories never appear.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import categories as categories_repo
from tests.auth_support import seed_login_user
from tests.contract.test_plan_support import USER_ID
from tests.ui_map import _html, plan_budget, plan_year

pytest_plugins = ("tests.contract.test_plan_support",)

BUDGET = "/plan?tab=budget&year=2026&month=3"
YEAR = "/plan?tab=year&year=2026"
LATE_BUDGET = "/plan?tab=budget&year=2099&month=1"
LATE_YEAR = "/plan?tab=year&year=2099"


@pytest.fixture
def world(db: sqlite3.Connection) -> None:
    """Unused (live), Old (archived), Other (second user's); no ledger rows at all."""
    categories_repo.create(db, USER_ID, NewCategory(name="Unused", direction=Direction.EXPENSE))
    old = categories_repo.create(db, USER_ID, NewCategory(name="Old", direction=Direction.EXPENSE))
    categories_repo.soft_delete(db, USER_ID, old.id)
    seed_login_user(db, user_id=2, email="other@example.com")
    categories_repo.create(db, 2, NewCategory(name="Other", direction=Direction.EXPENSE))
    db.commit()


def test_budget_lists_an_unused_unbudgeted_category(client: TestClient, world: None) -> None:
    page = client.get(BUDGET).text

    cells = _html.texts(page, plan_budget.row_cells("Unused"))
    assert cells[0] == "Unused"
    assert "0.00" in " ".join(cells)
    assert _html.count(page, plan_budget.set_budget_button("Unused")) == 1
    assert _html.count(page, plan_budget.edit_budget_item("Unused")) == 0


def test_budget_omits_archived_before_the_month_and_other_users(
    client: TestClient, world: None
) -> None:
    page = client.get(LATE_BUDGET).text

    assert _html.count(page, plan_budget.row("Unused")) == 1
    assert _html.count(page, plan_budget.row("Old")) == 0
    assert _html.count(page, plan_budget.row("Other")) == 0


def test_year_lists_an_unused_unbudgeted_category_as_a_row(client: TestClient, world: None) -> None:
    page = client.get(YEAR).text

    assert _html.count(page, plan_year.row("Unused")) == 1
    assert len(_html.resolve(page, plan_year.row_cells("Unused"))) == 12
    assert _html.count(page, plan_year.row("Other")) == 0


def test_year_omits_archived_before_the_year_and_other_users(
    client: TestClient, world: None
) -> None:
    page = client.get(LATE_YEAR).text

    assert _html.count(page, plan_year.row("Unused")) == 1
    assert _html.count(page, plan_year.row("Old")) == 0
    assert _html.count(page, plan_year.unbudgeted("Old")) == 0
    assert _html.count(page, plan_year.row("Other")) == 0
