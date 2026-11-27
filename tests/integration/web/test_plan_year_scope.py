"""Year grid inline cell editor: scope chips and the one save path (T-UR56, F4.8a).

World (2026, PLN): Groceries default 500.00, one-off March 321.00, recurring June 700.00. The
editor form is a template cloned by app-year-cell.js; the cell link carries the scope it
preselects and the text of its ``every <month>`` chip.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from budget_planner.domain.budgets import (
    NewBudgetDefault,
    NewBudgetOneOffOverride,
    NewBudgetRecurringOverride,
)
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.repositories import budgets as budgets_repo, categories as categories_repo
from tests.auth_support import seed_login_user
from tests.contract.test_plan_support import audit_total
from tests.ui_map import _html, plan_year

pytest_plugins = ("tests.contract.test_plan_support",)

URL = "/plan?tab=year&year=2026"
USER_ID = 1
SAVED = 61_234


@pytest.fixture
def groceries(db: sqlite3.Connection, cat_id: int) -> int:
    budgets_repo.set_default(db, USER_ID, NewBudgetDefault(category_id=cat_id, amount=50_000))
    budgets_repo.set_one_off(
        db, USER_ID, NewBudgetOneOffOverride(category_id=cat_id, year=2026, month=3, amount=32_100)
    )
    budgets_repo.set_recurring(
        db, USER_ID, NewBudgetRecurringOverride(category_id=cat_id, month=6, amount=70_000)
    )
    return cat_id


def _post(client: TestClient, category: int, **fields: str) -> int:
    form = {"year": "2026", "month": "4", "amount": "612.34", **fields}
    return client.post(f"/budget/rules/{category}/overrides", data=form).status_code


def test_editor_form_has_exactly_the_two_scope_chips(client: TestClient, groceries: int) -> None:
    page = client.get(URL).text

    group = _html.resolve_one(page, plan_year.cell_scope_group)
    chips = [
        (r.get("name"), r.get("value"), r.has_attr("checked")) for r in group.find_all("input")
    ]
    assert chips == [("tier", "one-off", True), ("tier", "recurring", False)]
    assert _html.count(page, plan_year.cell_scope("this month only")) == 1
    assert _html.count(page, plan_year.cell_scope("every month (default)")) == 0
    assert _html.count(page, plan_year.cell_scope("every month")) == 0


@pytest.mark.parametrize(
    ("month", "label"),
    [("March", "every march"), ("June", "every june"), ("January", "every january")],
)
def test_every_cell_opens_on_this_month_only_and_labels_its_month(
    client: TestClient, groceries: int, month: str, label: str
) -> None:
    page = client.get(URL).text

    cell = _html.resolve_one(page, plan_year.cell("Groceries", month))
    assert "tier=one-off" in cell["href"]
    assert "data-scope" not in cell.attrs
    assert cell["data-recurring-label"] == label


def test_default_scope_from_the_year_cell_is_a_visible_422_and_writes_nothing(
    client: TestClient, db: sqlite3.Connection, groceries: int
) -> None:
    before = audit_total(db)
    r = client.post(
        f"/budget/rules/{groceries}/overrides",
        data={"year": "2026", "month": "4", "amount": "1.00", "tier": "default", "origin": "year"},
    )

    assert r.status_code == 422
    assert _html.error_lines(r.text) != {}
    assert audit_total(db) == before
    default = budgets_repo.get_default(db, USER_ID, groceries)
    assert default is not None
    assert default.amount == 50_000


def test_inline_save_every_month_default_writes_the_default(
    client: TestClient, db: sqlite3.Connection, groceries: int
) -> None:
    before = audit_total(db)
    assert _post(client, groceries, tier="default") == 200

    default = budgets_repo.get_default(db, USER_ID, groceries)
    assert default is not None
    assert default.amount == SAVED
    assert budgets_repo.get_one_off(db, USER_ID, groceries, 2026, 4) is None
    assert budgets_repo.get_recurring(db, USER_ID, groceries, 4) is None
    assert audit_total(db) == before + 1


def test_inline_save_every_month_writes_the_recurring_tier(
    client: TestClient, db: sqlite3.Connection, groceries: int
) -> None:
    other = seed_login_user(db, user_id=2, email="mallory@example.test")
    theirs = categories_repo.create(
        db, other, NewCategory(name="Theirs", direction=Direction.EXPENSE)
    )
    assert _post(client, groceries, tier="recurring") == 200

    row = budgets_repo.get_recurring(db, USER_ID, groceries, 4)
    assert row is not None
    assert row.amount == SAVED
    assert budgets_repo.get_one_off(db, USER_ID, groceries, 2026, 4) is None
    assert budgets_repo.list_one_off(db, other) == []
    assert budgets_repo.get_recurring(db, other, theirs.id, 4) is None


def test_inline_save_this_month_only_writes_a_one_off(
    client: TestClient, db: sqlite3.Connection, groceries: int
) -> None:
    assert _post(client, groceries, tier="one-off") == 200

    row = budgets_repo.get_one_off(db, USER_ID, groceries, 2026, 4)
    assert row is not None
    assert row.amount == SAVED
    assert budgets_repo.get_recurring(db, USER_ID, groceries, 4) is None


def test_unknown_scope_is_a_visible_422_and_writes_nothing(
    client: TestClient, db: sqlite3.Connection, groceries: int
) -> None:
    before = audit_total(db)
    r = client.post(
        f"/budget/rules/{groceries}/overrides",
        data={"year": "2026", "month": "4", "amount": "1.00", "tier": "forever"},
    )

    assert r.status_code == 422
    assert _html.error_lines(r.text) != {}
    assert audit_total(db) == before
    assert budgets_repo.get_one_off(db, USER_ID, groceries, 2026, 4) is None
