"""Year grid and budget override dialogs: tiers, remove and period navigation (T-UR11b).

A plain click on a year cell edits it in place (one-off); a Shift click opens the override dialog,
whose scope radio picks the stored row (this month only, every <month>,
every month (default)). A saved or removed override closes the dialog and reloads the grid.
"""

from __future__ import annotations

from typing import Any

import pytest
from playwright.sync_api import expect

from tests.e2e.journeys._world import World, today
from tests.e2e.ui_actions import quiesce
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
    world.find(plan_year.cell("Groceries", "March")).click(modifiers=["Shift"])  # the dialog
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
    _override_in_march(world, "every month (default)", "650.00")

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

    # The save closed the dialog and the grid reload may still be in flight: a click on the
    # cell before it settles lands on the element about to be replaced and opens nothing.
    expect(world.find(plan_year.cell("Groceries", "March"))).to_have_text("• 321.00")
    quiesce(world.page)
    world.find(plan_year.cell("Groceries", "March")).click(modifiers=["Shift"])  # the dialog
    dialog = plan_year.dialog("Groceries", f"Mar {year}")
    expect(world.find(dialog)).to_be_visible()
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


def test_year_cell_edits_in_place_and_saves_a_one_off_on_enter(world: World) -> None:
    category = _budgeted(world)
    year = today().year
    world.goto("/plan?tab=year")
    world.find(plan_year.cell("Groceries", "March")).click()
    editor = world.find(plan_year.cell_editor("Groceries", "March"))
    expect(editor).to_have_value("500.00")
    world.find(plan_year.cell_scope("this month only")).check(force=True)  # visually hidden radio
    editor.fill("321.00")
    editor.press("Enter")

    row = world.wait_rows(
        "SELECT * FROM budget_one_off_overrides WHERE category_id = ? AND deleted_at IS NULL",
        (category,),
    )[0]
    assert (row["year"], row["month"], row["amount"]) == (year, MARCH, 32100)
    expect(world.find(plan_year.cell("Groceries", "March"))).to_have_text("• 321.00")
    expect(world.find(plan_year.cell_editor("Groceries", "March"))).to_have_count(0)


def test_year_cell_editor_preselects_the_cells_tier_and_labels_the_chips(world: World) -> None:
    _budgeted(world)
    world.goto("/plan?tab=year")
    world.find(plan_year.cell("Groceries", "March")).click()

    expect(world.find(plan_year.cell_scope("every month (default)"))).to_be_checked()
    expect(world.find(plan_year.cell_scope("every march"))).not_to_be_checked()
    expect(world.find(plan_year.cell_scope("this month only"))).not_to_be_checked()


_CHIP_GEOMETRY = """() => {
  const box = (el) => { const r = el.getBoundingClientRect();
    return {l: r.left, t: r.top, r: r.right, b: r.bottom}; };
  const group = document.querySelector('[role="radiogroup"][aria-label="budget scope"]');
  const chip = box(group);
  const hit = [...document.querySelectorAll('.rd-year-cell')]
    .filter((c) => c.getClientRects().length)
    .map((c) => ({name: c.getAttribute('aria-label'), ...box(c)}))
    .filter((c) => c.l < chip.r && c.r > chip.l && c.t < chip.b && c.b > chip.t)
    .map((c) => c.name);
  const chips = [...group.querySelectorAll('label')].map(box);
  return {hit, chips, width: window.innerWidth};
}"""


def _chip_geometry(world: World, width: int, month: str) -> dict[str, Any]:
    world.page.set_viewport_size({"width": width, "height": 900})
    _budgeted(world)
    world.post(f"/budget/defaults/{world.category('Rent')}", {"amount": "1200.00"})
    world.goto("/plan?tab=year")
    world.find(plan_year.cell("Groceries", month)).click()
    expect(world.find(plan_year.cell_scope("every month (default)"))).to_be_checked()
    geometry: dict[str, Any] = world.page.evaluate(_CHIP_GEOMETRY)
    return geometry


def test_year_cell_chip_row_covers_no_cell_value_at_desktop(world: World) -> None:
    geometry = _chip_geometry(world, 1440, "March")

    assert geometry["hit"] == []


def test_year_cell_chips_stay_inside_the_phone_viewport(world: World) -> None:
    geometry = _chip_geometry(world, 375, "December")

    assert geometry["hit"] == []
    assert len(geometry["chips"]) == 3
    for chip in geometry["chips"]:
        assert chip["l"] >= 0
        assert chip["r"] <= geometry["width"]


def test_year_cell_every_month_default_changes_every_months_cell(world: World) -> None:
    category = _budgeted(world)
    world.goto("/plan?tab=year")
    world.find(plan_year.cell("Groceries", "March")).click()
    editor = world.find(plan_year.cell_editor("Groceries", "March"))
    editor.fill("612.34")
    editor.press("Enter")

    for month in ("January", "March", "December"):
        expect(world.find(plan_year.cell("Groceries", month))).to_have_text("612.34")
    assert (
        world.scalar("SELECT amount FROM budget_defaults WHERE category_id = ?", (category,))
        == 61234
    )
    assert world.scalar("SELECT COUNT(*) FROM budget_one_off_overrides") == 0


def test_year_cell_editor_escape_cancels_without_saving(world: World) -> None:
    _budgeted(world)
    world.goto("/plan?tab=year")
    world.find(plan_year.cell("Groceries", "March")).click()
    editor = world.find(plan_year.cell_editor("Groceries", "March"))
    editor.fill("321.00")
    editor.press("Escape")

    expect(world.find(plan_year.cell_editor("Groceries", "March"))).to_have_count(0)
    expect(world.find(plan_year.cell("Groceries", "March"))).to_have_text("500.00")
    assert world.scalar("SELECT COUNT(*) FROM budget_one_off_overrides") == 0


def test_year_cell_editor_shows_the_error_of_a_failed_save(world: World) -> None:
    _budgeted(world)
    year = today().year
    world.goto("/plan?tab=year")
    world.find(plan_year.cell("Groceries", "March")).click()
    editor = world.find(plan_year.cell_editor("Groceries", "March"))
    editor.fill("1.2.3")
    editor.press("Enter")

    dialog = plan_year.dialog("Groceries", f"Mar {year}")
    expect(world.find(dialog)).to_be_visible()
    expect(world.find(rd_dialogs.field_error(dialog, "amount"))).to_contain_text(
        "enter an amount of 0 or more"
    )
    assert world.scalar("SELECT COUNT(*) FROM budget_one_off_overrides") == 0
