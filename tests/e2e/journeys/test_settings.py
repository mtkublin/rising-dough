"""Settings journeys: category CRUD + archive, FX tab, preferences (T-UT08b)."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.e2e.journeys._world import World
from tests.ui_map import ledger, settings

pytestmark = pytest.mark.e2e


def test_create_category_adds_a_settings_row(world: World) -> None:
    world.goto("/settings?tab=categories")
    world.find(settings.new_category).click()
    world.find(settings.form_name).fill("Pets")
    world.find(settings.form_expense).check()
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


def test_archive_category_then_restore_from_recently_deleted(world: World) -> None:
    category = world.category("Hobby")
    world.goto("/settings?tab=categories")
    world.find(settings.archive_category(category)).click()  # native confirm is accepted

    world.wait_rows("SELECT 1 FROM categories WHERE id = ? AND deleted_at IS NOT NULL", (category,))
    expect(world.find(settings.category_row(category))).to_have_count(0)
    world.find(ledger.recently_deleted_link).click()
    world.settle()
    world.find(ledger.restore("category", category)).click()

    world.wait_rows("SELECT 1 FROM categories WHERE id = ? AND deleted_at IS NULL", (category,))
    assert world.audit_ops("category", category) == ["create", "delete", "undelete"]
    world.goto("/settings?tab=categories")
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
    expect(world.find(settings.fx_row("EUR → PLN"))).to_contain_text("4.250000")


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
