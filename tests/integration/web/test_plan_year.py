"""GET /plan?tab=year renders the Rising Dough year grid with exact values (T-UR11, ADR-0107).

World (all PLN, year 2026): Groceries default 500.00, one-off March 321.00, recurring June 700.00;
Rent default 1,200.50 and a one-off of 0.00 in January (zero is a value, ADR-0136); Gym has no
budget at all; archived Old gym is covered by the service tests. A second user's Secret category
carries a budget that must never show.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner.domain.budgets import (
    NewBudgetDefault,
    NewBudgetOneOffOverride,
    NewBudgetRecurringOverride,
)
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    budgets as budgets_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from budget_planner.web.plan_year_view import (
    TIER_DEFAULT,
    TIER_ONE_OFF,
    TIER_RECURRING,
    tier_labels,
)
from tests.auth_support import seed_login_user
from tests.ui_map import _html, plan_budget, plan_year

pytest_plugins = ("tests.contract.test_plan_support",)

URL = "/plan?tab=year&year=2026"
USER_ID = 1
GROCERIES_DEFAULT = 50_000
RENT_DEFAULT = 120_050


@pytest.fixture
def world(db: sqlite3.Connection, cat_id: int) -> dict[str, int]:
    """Groceries is ``cat_id``; returns the category ids by name."""
    rent = categories_repo.create(
        db, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    )
    gym = categories_repo.create(db, USER_ID, NewCategory(name="Gym", direction=Direction.EXPENSE))
    budgets_repo.set_default(
        db, USER_ID, NewBudgetDefault(category_id=cat_id, amount=GROCERIES_DEFAULT)
    )
    budgets_repo.set_one_off(
        db, USER_ID, NewBudgetOneOffOverride(category_id=cat_id, year=2026, month=3, amount=32_100)
    )
    budgets_repo.set_recurring(
        db, USER_ID, NewBudgetRecurringOverride(category_id=cat_id, month=6, amount=70_000)
    )
    budgets_repo.set_default(
        db, USER_ID, NewBudgetDefault(category_id=rent.id, amount=RENT_DEFAULT)
    )
    budgets_repo.set_one_off(
        db, USER_ID, NewBudgetOneOffOverride(category_id=rent.id, year=2026, month=1, amount=0)
    )
    return {"Groceries": cat_id, "Rent": rent.id, "Gym": gym.id}


def _texts(page: str, name: str) -> list[str]:
    return _html.texts(page, plan_year.row_cells(name))


def _states(page: str, name: str) -> list[str]:
    return [str(a.get("data-state")) for a in _html.resolve(page, plan_year.row_cells(name))]


def test_groceries_row_prints_each_tier(client: TestClient, world: dict[str, int]) -> None:
    page = client.get(URL).text

    texts = _texts(page, "Groceries")
    assert len(texts) == 12
    assert texts[0] == "500.00"
    assert texts[2] == "• 321.00"
    assert texts[5] == "↻ 700.00"
    assert _states(page, "Groceries")[:6] == [
        "default",
        "default",
        "one-off",
        "default",
        "default",
        "recurring",
    ]
    # the recurring override applies to June of every year, not only this one
    assert _texts(client.get("/plan?tab=year&year=2027").text, "Groceries")[5] == "↻ 700.00"


def test_rent_row_prints_a_zero_override_not_the_default(
    client: TestClient, world: dict[str, int]
) -> None:
    page = client.get(URL).text

    texts = _texts(page, "Rent")
    assert texts[:3] == ["• 0.00", "1,200.50", "1,200.50"]
    assert _states(page, "Rent")[:2] == ["one-off", "default"]


def test_cell_has_a_spoken_name_and_opens_its_dialog(
    client: TestClient, world: dict[str, int]
) -> None:
    page = client.get(URL).text

    march = _html.resolve_one(page, plan_year.cell("Groceries", "March"))
    assert march["aria-label"] == "Groceries, March: 321.00 PLN, one-off override"
    url = f"/budget/rules/{world['Groceries']}/overrides/new?year=2026&month=3&tier=one-off"
    assert (march["href"], march["hx-get"], march["hx-target"]) == (url, url, "#modal-root")
    june = _html.resolve_one(page, plan_year.cell("Groceries", "June"))
    assert str(june["href"]).endswith("?year=2026&month=6&tier=recurring")
    january = _html.resolve_one(page, plan_year.cell("Groceries", "January"))
    assert str(january["href"]).endswith("?year=2026&month=1&tier=default")


def test_category_without_a_budget_is_listed_in_the_disclosure(
    client: TestClient, db: sqlite3.Connection, account_id: int, world: dict[str, int]
) -> None:
    # R14 (2026-11-27): a category without a budget is listed in the disclosure with or without
    # ledger entries, never as a grid row.
    before = client.get(URL).text
    assert _html.count(before, plan_year.row("Gym")) == 0
    assert _html.texts(before, plan_year.unbudgeted("Gym")) == ["Gym"]
    transactions_repo.create(
        db,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 5, 4),
            category_id=world["Gym"],
            account_id=account_id,
            amount=4_000,
            description="gym pass",
        ),
    )
    page = client.get(URL).text

    assert _html.count(page, plan_year.row("Gym")) == 0
    assert _html.texts(page, plan_year.unbudgeted("Gym")) == ["Gym"]
    assert _html.text_of(page, plan_year.disclosure) == "1 category without a budget"
    link = _html.resolve_one(page, plan_year.unbudgeted("Gym"))
    assert str(link["href"]).startswith(
        f"/budget/rules/{world['Gym']}/overrides/new?year=2026&month="
    )
    assert str(link["href"]).endswith("&tier=default")


def test_grid_has_one_row_per_budgeted_category_and_twelve_month_headings(
    client: TestClient, world: dict[str, int]
) -> None:
    page = client.get(URL).text

    names = [_html.accessible_name(r) for r in _html.resolve(page, plan_year.rows)]
    assert len(names) == 3  # head row, Groceries, Rent
    assert _html.count(page, plan_year.month_headers) == 12
    assert _html.text_of(page, plan_year.heading) == "Yearly budget"


def test_period_nav_steps_the_year(client: TestClient, world: dict[str, int]) -> None:
    page = client.get(URL).text

    prev = _html.resolve_one(page, plan_year.period_prev)
    nxt = _html.resolve_one(page, plan_year.period_next)
    assert prev["href"] == "/plan?tab=year&year=2025"
    assert nxt["href"] == "/plan?tab=year&year=2027"
    assert _html.texts(page, plan_year.picker_years) == ["2025", "2026", "2027"]
    assert _html.resolve_one(page, plan_budget.tab("year")).get("aria-current") == "page"


def test_second_users_budget_is_absent(
    client: TestClient, db: sqlite3.Connection, world: dict[str, int]
) -> None:
    other = seed_login_user(db, user_id=2, email="mallory@example.test")
    secret = categories_repo.create(
        db, other, NewCategory(name="Secret", direction=Direction.EXPENSE)
    )
    budgets_repo.set_default(db, other, NewBudgetDefault(category_id=secret.id, amount=999_99))

    page = client.get(URL).text

    assert _html.count(page, plan_year.row("Secret")) == 0
    assert _html.count(page, plan_year.unbudgeted("Secret")) == 0
    assert "999.99" not in _html.all_text(page, plan_year.panel)


def test_empty_year_lists_no_rows(client: TestClient) -> None:
    page = client.get(URL).text

    assert _html.count(page, plan_year.cells) == 0
    assert _html.count(page, plan_year.disclosure) == 0


def test_scope_chips_print_the_tier_labels_of_the_override_dialog(
    client: TestClient, world: dict[str, int]
) -> None:
    page = client.get(URL).text
    labels = tier_labels(1)

    for tier in (TIER_ONE_OFF, TIER_DEFAULT):
        chip = _html.resolve_one(page, plan_year.cell_scope(labels[tier]))
        assert chip["value"] == tier
    january = _html.resolve_one(page, plan_year.cell("Groceries", "January"))
    assert january["data-recurring-label"] == labels[TIER_RECURRING] == "every january"


def test_default_cell_link_opens_the_dialog_on_the_tier_the_editor_preselects(
    client: TestClient, world: dict[str, int]
) -> None:
    page = client.get(URL).text
    january = _html.resolve_one(page, plan_year.cell("Groceries", "January"))

    assert january["data-scope"] == "default"
    assert str(january["href"]).endswith("&tier=default")
    dialog = client.get(str(january["href"])).text
    scope = plan_year.dialog("Groceries", "Jan 2026")
    checked = [
        label
        for label in ("this month only", "every january", "every month (default)")
        if _html.resolve_one(dialog, plan_year.tier(scope, label)).has_attr("checked")
    ]
    assert checked == ["every month (default)"]
