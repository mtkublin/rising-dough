"""Budget override tiers (month / every / default) and period navigation (T-UT08b)."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.e2e.journeys._world import World, today
from tests.ui_map import plan

pytestmark = pytest.mark.e2e

MARCH = 3


def _budgeted(world: World) -> int:
    world.account()
    category = world.category("Groceries")
    world.post(f"/budget/defaults/{category}", {"amount": "500.00"})
    return category


def _override_in_march(world: World, category: int, tier: str, amount: str) -> int:
    year = today().year
    world.goto("/plan?tab=year")
    cell = plan.year_cell(category, MARCH)
    world.find(plan.year_cell_button("Groceries", "Mar", year)).click()
    world.find(plan.tier(cell, tier)).dispatch_event("click")  # sr-only radio in a styled label
    world.find(plan.cell_amount(cell)).fill(amount)
    world.find(plan.cell_save(cell)).click()
    return year


def test_override_this_month_only_writes_a_one_off(world: World) -> None:
    category = _budgeted(world)
    year = _override_in_march(world, category, "This month only", "321.00")

    row = world.wait_rows(
        "SELECT * FROM budget_one_off_overrides WHERE category_id = ? AND deleted_at IS NULL",
        (category,),
    )[0]
    assert (row["year"], row["month"], row["amount"]) == (year, MARCH, 32100)
    assert world.scalar("SELECT COUNT(*) FROM budget_recurring_overrides") == 0
    assert (
        world.scalar("SELECT amount FROM budget_defaults WHERE category_id = ?", (category,))
        == 50000
    )
    expect(world.find(plan.year_cell(category, MARCH))).to_contain_text("321")


def test_override_every_month_writes_a_recurring_override(world: World) -> None:
    category = _budgeted(world)
    _override_in_march(world, category, "Every Mar", "222.00")

    row = world.wait_rows(
        "SELECT * FROM budget_recurring_overrides WHERE category_id = ? AND deleted_at IS NULL",
        (category,),
    )[0]
    assert (row["month"], row["amount"]) == (MARCH, 22200)
    assert world.scalar("SELECT COUNT(*) FROM budget_one_off_overrides") == 0
    expect(world.find(plan.year_cell(category, MARCH))).to_contain_text("222")


def test_override_new_default_replaces_the_default(world: World) -> None:
    category = _budgeted(world)
    _override_in_march(world, category, "New default", "650.00")

    world.wait_rows(
        "SELECT 1 FROM budget_defaults WHERE category_id = ? AND amount = 65000 "
        "AND deleted_at IS NULL",
        (category,),
    )
    assert world.scalar("SELECT COUNT(*) FROM budget_one_off_overrides") == 0
    assert world.scalar("SELECT COUNT(*) FROM budget_recurring_overrides") == 0
    expect(world.find(plan.year_cell(category, MARCH))).to_contain_text("650")


def test_year_tab_navigation_steps_years(world: World) -> None:
    world.goto("/plan?tab=year&year=2026")
    expect(world.find(plan.heading)).to_contain_text("2026")
    world.find(plan.year_nav_previous).click()
    expect(world.find(plan.heading)).to_contain_text("2025")
    world.find(plan.year_nav_next).click()
    world.find(plan.year_nav_next).click()
    expect(world.find(plan.heading)).to_contain_text("2027")
