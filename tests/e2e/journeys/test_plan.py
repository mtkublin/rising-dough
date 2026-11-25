"""Year grid and budget override dialogs: tiers, remove and period navigation (T-UR11b).

The year cell opens the override dialog; the scope radio picks the stored row (this month only,
every <month>, new default). A saved or removed override closes the dialog and reloads the grid.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.e2e.journeys._world import World, today
from tests.ui_map import plan_year, rd_dialogs

pytestmark = pytest.mark.e2e

MARCH = 3


def _budgeted(world: World) -> int:
    world.account()
    category = world.category("Groceries")
    world.post(f"/budget/defaults/{category}", {"amount": "500.00"})
    return category


def _open_march(world: World) -> int:
    year = today().year
    world.goto("/plan?tab=year")
    world.find(plan_year.cell("Groceries", "March")).click()
    expect(world.find(plan_year.dialog("Groceries", f"Mar {year}"))).to_be_visible()
    return year


def _override_in_march(world: World, tier: str, amount: str) -> int:
    year = _open_march(world)
    dialog = plan_year.dialog("Groceries", f"Mar {year}")
    world.find(plan_year.tier(dialog, tier)).dispatch_event("click")  # visually hidden radio
    world.find(plan_year.amount(dialog)).fill(amount)
    world.find(plan_year.save(dialog)).click()
    expect(world.find(dialog)).to_have_count(0)
    return year


def test_override_this_month_only_writes_a_one_off(world: World) -> None:
    category = _budgeted(world)
    year = _override_in_march(world, "this month only", "321.00")

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
    expect(world.find(plan_year.cell("Groceries", "March"))).to_have_text("• 321.00")


def test_override_every_month_writes_a_recurring_override(world: World) -> None:
    category = _budgeted(world)
    _override_in_march(world, "every march", "222.00")

    row = world.wait_rows(
        "SELECT * FROM budget_recurring_overrides WHERE category_id = ? AND deleted_at IS NULL",
        (category,),
    )[0]
    assert (row["month"], row["amount"]) == (MARCH, 22200)
    assert world.scalar("SELECT COUNT(*) FROM budget_one_off_overrides") == 0
    expect(world.find(plan_year.cell("Groceries", "March"))).to_have_text("↻ 222.00")


def test_override_new_default_replaces_the_default(world: World) -> None:
    category = _budgeted(world)
    _override_in_march(world, "new default", "650.00")

    world.wait_rows(
        "SELECT 1 FROM budget_defaults WHERE category_id = ? AND amount = 65000 "
        "AND deleted_at IS NULL",
        (category,),
    )
    assert world.scalar("SELECT COUNT(*) FROM budget_one_off_overrides") == 0
    assert world.scalar("SELECT COUNT(*) FROM budget_recurring_overrides") == 0
    expect(world.find(plan_year.cell("Groceries", "March"))).to_have_text("650.00")


def test_removing_an_override_restores_the_default(world: World) -> None:
    category = _budgeted(world)
    year = _override_in_march(world, "this month only", "321.00")
    world.wait_rows("SELECT 1 FROM budget_one_off_overrides WHERE deleted_at IS NULL")

    world.find(plan_year.cell("Groceries", "March")).click()
    dialog = plan_year.dialog("Groceries", f"Mar {year}")
    world.find(plan_year.remove_override(dialog)).click()
    confirm = plan_year.remove_dialog()
    expect(world.find(confirm)).to_contain_text("goes back to the default 500.00 PLN")
    world.find(plan_year.confirm_remove(confirm)).click()

    expect(world.find(confirm)).to_have_count(0)
    expect(world.find(plan_year.cell("Groceries", "March"))).to_have_text("500.00")
    assert (
        world.scalar(
            "SELECT COUNT(*) FROM budget_one_off_overrides WHERE category_id = ? "
            "AND deleted_at IS NOT NULL",
            (category,),
        )
        == 1
    )


def test_invalid_amount_keeps_the_dialog_open_with_the_field_error(world: World) -> None:
    _budgeted(world)
    year = _open_march(world)
    dialog = plan_year.dialog("Groceries", f"Mar {year}")
    world.find(plan_year.amount(dialog)).fill("1.2.3")
    world.find(plan_year.save(dialog)).click()

    expect(world.find(dialog)).to_be_visible()
    expect(world.find(rd_dialogs.field_error(dialog, "amount"))).to_contain_text(
        "enter an amount of 0 or more"
    )
    assert world.scalar("SELECT COUNT(*) FROM budget_one_off_overrides") == 0


def test_year_tab_navigation_steps_years(world: World) -> None:
    world.goto("/plan?tab=year&year=2026")
    expect(world.find(plan_year.period_label)).to_contain_text("2026")
    world.find(plan_year.period_prev).click()
    expect(world.find(plan_year.period_label)).to_contain_text("2025")
    world.find(plan_year.period_next).click()
    world.find(plan_year.period_next).click()
    expect(world.find(plan_year.period_label)).to_contain_text("2027")
