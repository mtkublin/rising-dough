"""Settings journeys: category CRUD + archive, FX tab, preferences (T-UT08b)."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.e2e.journeys._world import World
from tests.ui_map import settings, shell

pytestmark = pytest.mark.e2e


def test_create_category_adds_a_settings_row(world: World) -> None:
    world.goto("/settings?tab=categories")
    world.find(settings.new_category).click()
    world.find(settings.form_name).fill("Pets")
    world.find(settings.form_expense).check(force=True)  # the radio is visually hidden
    world.find(settings.form_create).click()

    row = world.wait_rows("SELECT * FROM categories WHERE name = 'Pets'")[0]
    assert (row["direction"], row["deleted_at"], row["is_system"]) == ("expense", None, 0)
    assert world.audit_ops("category", row["id"]) == ["create"]
    expect(world.find(settings.category_row(row["id"]))).to_contain_text("Pets")


def test_edit_category_renames_it(world: World) -> None:
    category = world.category("Petss")
    world.goto("/settings?tab=categories")
    world.find(settings.edit_category(category)).click()
    world.find(settings.edit_form_name).fill("Pets")
    world.find(settings.edit_form_save).click()

    world.wait_rows("SELECT 1 FROM categories WHERE id = ? AND name = 'Pets'", (category,))
    assert world.audit_ops("category", category) == ["create", "update"]
    expect(world.find(settings.category_row(category))).to_contain_text("Pets")


def test_archive_category_closes_the_dialog_shows_undo_then_restore(world: World) -> None:
    category = world.category("Hobby")
    world.goto("/settings?tab=categories")
    world.find(settings.archive_category(category)).click()
    expect(world.find(settings.archive_dialog)).to_be_visible()
    world.find(settings.archive_confirm).click()

    world.wait_rows("SELECT 1 FROM categories WHERE id = ? AND deleted_at IS NOT NULL", (category,))
    # ADR-0152: the 204 closes the confirm dialog via the dialog-close event; the toast offers undo.
    expect(world.find(settings.archive_dialog)).to_have_count(0)
    expect(world.find(shell.undo_button)).to_be_visible()
    expect(world.find(settings.category_row(category))).to_have_count(0)  # list refetched
    world.find(shell.undo_button).click()  # restores and reloads the page

    world.wait_rows("SELECT 1 FROM categories WHERE id = ? AND deleted_at IS NULL", (category,))
    assert world.audit_ops("category", category) == ["create", "delete", "undelete"]
    expect(world.find(settings.category_row(category))).to_contain_text("Hobby")


def test_fx_tab_lists_cached_rates(world: World) -> None:
    world.goto("/settings?tab=categories")
    world.find(settings.tab("Currency & FX")).click()
    expect(world.find(settings.fx_heading)).to_be_visible()
    expect(world.find(settings.fx_table)).to_have_count(0)  # nothing cached on a fresh DB
    assert world.scalar("SELECT COUNT(*) FROM fx_rates") == 0

    world.write(
        "INSERT INTO fx_rates (date, from_ccy, to_ccy, rate) "
        "VALUES ('2026-01-05', 'EUR', 'PLN', '4.25')"
    )
    world.goto("/settings?tab=fx")
    expect(world.find(settings.fx_row("EUR → PLN"))).to_contain_text("4.25")


def test_preferences_show_base_currency_and_save_the_income_anchor(world: World) -> None:
    world.goto("/settings?tab=categories")
    world.find(settings.tab("Preferences")).click()
    expect(world.find(settings.prefs_panel_heading)).to_be_visible()
    expect(world.find(settings.pref_values).first).to_contain_text("PLN")

    salary = world.category("Salary", "income")
    world.goto("/settings?tab=categories")
    world.find(settings.income_anchor).select_option(str(salary))
    world.wait_rows("SELECT 1 FROM user_preferences WHERE value = ?", (str(salary),))
    world.goto("/settings?tab=categories")
    expect(world.find(settings.income_anchor)).to_have_value(str(salary))


def test_new_income_category_appears_in_the_income_anchor_without_reload(world: World) -> None:
    world.goto("/settings?tab=categories")
    world.find(settings.new_category).click()
    world.find(settings.form_name).fill("Bonus")
    world.find(settings.form_income).check(force=True)  # the radio is visually hidden
    world.find(settings.form_create).click()

    row = world.wait_rows("SELECT id FROM categories WHERE name = 'Bonus'")[0]
    expect(world.find(settings.category_row(row["id"]))).to_contain_text("Bonus")
    expect(world.find(settings.anchor_option("Bonus"))).to_have_count(1)
