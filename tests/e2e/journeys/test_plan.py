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
    expect(world.find(plan_year.cell_scope("this month only"))).to_be_checked()
    editor.fill("321.00")
    editor.press("Enter")

    row = world.wait_rows(
        "SELECT * FROM budget_one_off_overrides WHERE category_id = ? AND deleted_at IS NULL",
        (category,),
    )[0]
    assert (row["year"], row["month"], row["amount"]) == (year, MARCH, 32100)
    assert world.scalar("SELECT COUNT(*) FROM budget_recurring_overrides") == 0
    expect(world.find(plan_year.cell("Groceries", "March"))).to_have_text("• 321.00")
    expect(world.find(plan_year.cell_editor("Groceries", "March"))).to_have_count(0)
    expect(world.find(plan_year.cell("Groceries", "March"))).to_be_focused()


def test_year_cell_editor_offers_two_chips_and_this_month_is_preselected(world: World) -> None:
    _budgeted(world)
    world.goto("/plan?tab=year")
    world.find(plan_year.cell("Groceries", "March")).click()

    expect(world.find(plan_year.cell_scope("this month only"))).to_be_checked()
    expect(world.find(plan_year.cell_scope("every march"))).not_to_be_checked()
    expect(world.find(plan_year.cell_scope("every month (default)"))).to_have_count(0)
    expect(world.find(plan_year.cell_scope_chips)).to_have_count(2)


def test_year_cell_every_month_chip_saves_a_recurring_override_on_enter(world: World) -> None:
    category = _budgeted(world)
    world.goto("/plan?tab=year")
    world.find(plan_year.cell("Groceries", "March")).click()
    editor = world.find(plan_year.cell_editor("Groceries", "March"))
    editor.fill("612.34")
    world.find(plan_year.cell_scope("every march")).check(force=True)  # visually hidden radio
    editor.press("Enter")

    row = world.wait_rows(
        "SELECT * FROM budget_recurring_overrides WHERE category_id = ? AND deleted_at IS NULL",
        (category,),
    )[0]
    assert (row["month"], row["amount"]) == (MARCH, 61234)
    assert world.scalar("SELECT COUNT(*) FROM budget_one_off_overrides") == 0
    assert (
        world.scalar("SELECT amount FROM budget_defaults WHERE category_id = ?", (category,))
        == 50000
    )
    expect(world.find(plan_year.cell("Groceries", "March"))).to_have_text("↻ 612.34")


def test_year_cell_tab_goes_from_the_amount_to_the_scope_chips_and_back(world: World) -> None:
    category = _budgeted(world)
    world.goto("/plan?tab=year")
    world.find(plan_year.cell("Groceries", "March")).click()
    editor = world.find(plan_year.cell_editor("Groceries", "March"))
    this_month = world.find(plan_year.cell_scope("this month only"))
    expect(editor).to_be_focused()

    world.page.keyboard.press("Tab")
    expect(this_month).to_be_focused()
    world.page.keyboard.press("Shift+Tab")
    expect(editor).to_be_focused()

    world.page.keyboard.press("Tab")
    world.page.keyboard.press("ArrowRight")
    expect(world.find(plan_year.cell_scope("every march"))).to_be_focused()
    expect(world.find(plan_year.cell_scope("every march"))).to_be_checked()
    world.page.keyboard.press("Enter")

    row = world.wait_rows(
        "SELECT * FROM budget_recurring_overrides WHERE category_id = ? AND deleted_at IS NULL",
        (category,),
    )[0]
    assert (row["month"], row["amount"]) == (MARCH, 50000)


_ROW_TOPS = """() => [...document.querySelectorAll('table.rd-year tr')]
  .map((r) => r.getBoundingClientRect().top)"""

_CHIP_GEOMETRY = """() => {
  const box = (el) => { const r = el.getBoundingClientRect();
    return {l: r.left, t: r.top, r: r.right, b: r.bottom}; };
  const group = document.querySelector('[role="radiogroup"][aria-label="budget scope"]');
  const wrap = group.closest('td');
  return {
    group: box(group),
    wrap: box(wrap),
    chips: [...group.querySelectorAll('label')].map(box),
    width: window.innerWidth,
    boxed: getComputedStyle(group).borderTopWidth + '|' + getComputedStyle(group).backgroundColor,
  };
}"""


def _open_cell(world: World, width: int, month: str) -> None:
    world.page.set_viewport_size({"width": width, "height": 900})
    _budgeted(world)
    world.post(f"/budget/defaults/{world.category('Rent')}", {"amount": "1200.00"})
    world.goto("/plan?tab=year")
    world.find(plan_year.cell("Groceries", month)).click()
    expect(world.find(plan_year.cell_scope("this month only"))).to_be_checked()


def _assert_chips_under_cell_inside_viewport(geometry: dict[str, Any]) -> None:
    group, wrap = geometry["group"], geometry["wrap"]
    assert group["t"] >= wrap["b"] - 1  # hovers beneath the edited cell
    assert group["l"] < wrap["r"]  # and starts over it, not beside it
    assert group["r"] > wrap["l"]
    assert len(geometry["chips"]) == 2
    for chip in geometry["chips"]:
        assert chip["l"] >= 0
        assert chip["r"] <= geometry["width"]


@pytest.mark.parametrize("width", [1440, 375])
def test_year_cell_chips_hover_under_the_cell_and_shift_no_row(world: World, width: int) -> None:
    world.page.set_viewport_size({"width": width, "height": 900})
    _budgeted(world)
    world.post(f"/budget/defaults/{world.category('Rent')}", {"amount": "1200.00"})
    world.goto("/plan?tab=year")
    closed: list[float] = world.page.evaluate(_ROW_TOPS)
    world.find(plan_year.cell("Groceries", "March")).click()
    expect(world.find(plan_year.cell_scope("this month only"))).to_be_checked()

    opened: list[float] = world.page.evaluate(_ROW_TOPS)
    assert opened == closed
    geometry = world.page.evaluate(_CHIP_GEOMETRY)
    _assert_chips_under_cell_inside_viewport(geometry)
    assert geometry["boxed"] == "0px|rgba(0, 0, 0, 0)"  # no outer box around the chips


@pytest.mark.parametrize(
    ("width", "month"), [(1440, "January"), (1440, "December"), (375, "January"), (375, "December")]
)
def test_year_cell_chips_stay_inside_the_viewport_at_both_edges(
    world: World, width: int, month: str
) -> None:
    _open_cell(world, width, month)

    _assert_chips_under_cell_inside_viewport(world.page.evaluate(_CHIP_GEOMETRY))


def test_year_cell_chips_flip_above_the_cell_when_there_is_no_room_below(world: World) -> None:
    world.page.set_viewport_size({"width": 1440, "height": 900})
    _budgeted(world)
    world.goto("/plan?tab=year")
    world.find(plan_year.cell("Groceries", "March")).click()
    expect(world.find(plan_year.cell_scope("this month only"))).to_be_checked()
    cell_bottom = world.page.evaluate(_CHIP_GEOMETRY)["wrap"]["b"]
    # The viewport shrinks until the cell sits at its bottom edge; the resize handler re-places.
    world.page.set_viewport_size({"width": 1440, "height": int(cell_bottom) + 2})
    world.page.wait_for_timeout(200)

    geometry = world.page.evaluate(_CHIP_GEOMETRY)
    height = world.page.evaluate("window.innerHeight")
    assert geometry["wrap"]["b"] > height - 20  # the cell sits at the viewport bottom
    assert geometry["group"]["b"] <= height
    editor = world.find(plan_year.cell_editor("Groceries", "March")).bounding_box()
    assert editor is not None
    assert geometry["group"]["b"] <= editor["y"]  # above the edited cell, not over it
    assert geometry["group"]["b"] >= geometry["wrap"]["t"] - 8  # and right against it


def test_year_cell_chips_follow_a_horizontally_scrolled_grid_on_a_phone(world: World) -> None:
    world.page.set_viewport_size({"width": 375, "height": 900})
    _budgeted(world)
    world.goto("/plan?tab=year")
    world.page.evaluate("document.querySelector('.rd-year__scroll').scrollLeft = 220")
    cell = world.find(plan_year.cell("Groceries", "June"))
    cell.click()
    expect(world.find(plan_year.cell_scope("this month only"))).to_be_checked()

    _assert_chips_under_cell_inside_viewport(world.page.evaluate(_CHIP_GEOMETRY))


def _assert_attached(world: World) -> None:
    """The chip group sits right under the edited cell (above it when flipped), over its column."""
    g = world.page.evaluate(_CHIP_GEOMETRY)
    group, wrap = g["group"], g["wrap"]
    below = 0 <= group["t"] - wrap["b"] <= 8
    above = 0 <= wrap["t"] - group["b"] <= 8
    assert below or above, (group, wrap)
    assert group["l"] < wrap["r"]
    assert group["r"] > wrap["l"]
    for chip in g["chips"]:
        assert chip["l"] >= 0
        assert chip["r"] <= g["width"]


def test_year_cell_chips_stay_attached_on_a_phone_while_page_grid_and_keyboard_move(
    world: World,
) -> None:
    world.page.set_viewport_size({"width": 375, "height": 700})
    _budgeted(world)
    world.goto("/plan?tab=year")
    world.page.evaluate("document.querySelector('.rd-year__scroll').scrollLeft = 120")
    world.find(plan_year.cell("Groceries", "May")).click()
    expect(world.find(plan_year.cell_scope("this month only"))).to_be_checked()
    _assert_attached(world)

    world.page.evaluate("window.scrollBy(0, 60)")  # the page scrolls
    world.page.wait_for_timeout(100)
    _assert_attached(world)

    world.page.evaluate("document.querySelector('.rd-year__scroll').scrollLeft += 90")
    world.page.wait_for_timeout(100)  # the grid scrolls
    _assert_attached(world)

    # The on-screen keyboard or a pinch moves the visual viewport without a window scroll event:
    # the cell shifts in layout terms and only visualViewport events announce it.
    world.page.evaluate(
        """() => {
          document.querySelector('.rd-year__scroll').style.marginTop = '90px';
          window.visualViewport.dispatchEvent(new Event('resize'));
        }"""
    )
    world.page.wait_for_timeout(150)
    _assert_attached(world)
    world.page.keyboard.press("Escape")
    expect(world.find(plan_year.cell_scope_chips)).to_have_count(0)


_CHIP_COLOURS = """(theme) => {
  document.documentElement.dataset.theme = theme;
  const probe = (prop, token) => {
    const el = document.createElement('span');
    el.style.setProperty(prop, `var(${token})`);
    document.body.append(el);
    const value = getComputedStyle(el).getPropertyValue(prop);
    el.remove();
    return value;
  };
  const group = document.querySelector('[role="radiogroup"][aria-label="budget scope"]');
  const labels = [...group.querySelectorAll('label')];
  const idle = getComputedStyle(labels.find((l) => !l.querySelector('input').checked));
  const on = getComputedStyle(labels.find((l) => l.querySelector('input').checked));
  return {
    idle: [idle.color, idle.backgroundColor, idle.borderTopColor],
    idleWant: [probe('color', '--color-ink'), probe('background-color', '--color-panel'),
      probe('border-top-color', '--color-rule')],
    on: [on.color, on.backgroundColor, on.borderTopColor],
    onWant: [probe('color', '--color-ink'), probe('background-color', '--color-raised'),
      probe('border-top-color', '--color-ink')],
  };
}"""


def test_year_cell_chip_colours_follow_the_theme(world: World) -> None:
    _open_cell(world, 1440, "March")

    light = world.page.evaluate(_CHIP_COLOURS, "light")
    assert light["idle"] == light["idleWant"]
    assert light["on"] == light["onWant"]
    dark = world.page.evaluate(_CHIP_COLOURS, "dark")
    assert dark["idle"] == dark["idleWant"]
    assert dark["on"] == dark["onWant"]
    assert light["idleWant"] != dark["idleWant"]  # the tokens do switch with the theme


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
