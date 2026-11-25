"""New-entry journeys: happened, planned, repeats (fixed and formula) (T-UT08b).

Each journey drives the add-entry overlay through UI-map names and asserts the
row on screen plus the DB effect (the row, its amount in minor units).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.e2e.journeys._world import World, days_from_today
from tests.ui_map import ledger
from tests.ui_map.locator import Locator

pytestmark = pytest.mark.e2e

LEDGER_ALL_TIME = "/ledger?view=actual&date_from=2000-01-01&date_to=2099-12-31"


def _pick(world: World, field: Locator, option: str) -> None:
    box = world.find(ledger.overlay_field(field))
    box.click()
    box.fill(option)
    world.find(ledger.combo_option(option)).click()


def _open_overlay(world: World, tab: str) -> None:
    world.goto(LEDGER_ALL_TIME)
    world.find(ledger.add_new).click()
    expect(world.find(ledger.slideover)).to_be_visible()
    if tab != "Happened":
        world.find(ledger.entry_tab(tab)).click()
    expect(world.find(ledger.entry_tab(tab))).to_have_attribute("aria-selected", "true")


@pytest.mark.skip(reason="T-UR10b: legacy + Add overlay left the ledger; dialog journeys follow")
def test_new_happened_entry_lands_in_actual(world: World) -> None:
    account = world.account("Checking")
    category = world.category("Groceries")
    _open_overlay(world, "Happened")
    _pick(world, ledger.field_category, "Groceries")
    world.find(ledger.overlay_field(ledger.field_amount)).fill("12.50")
    _pick(world, ledger.field_account, "Checking")
    world.find(ledger.overlay_field(ledger.field_note)).fill("happened-entry")
    world.find(ledger.overlay_add_entry).click()

    txn = world.wait_rows("SELECT * FROM transactions WHERE description = 'happened-entry'")
    assert len(txn) == 1
    assert (txn[0]["amount"], txn[0]["account_id"], txn[0]["category_id"]) == (
        1250,
        account,
        category,
    )
    assert txn[0]["deleted_at"] is None
    assert world.audit_ops("transaction", txn[0]["id"]) == ["create"]
    expect(world.find(ledger.slideover)).to_have_count(0)  # saved: the overlay closes itself
    expect(world.find(ledger.row(txn[0]["id"]))).to_contain_text("happened-entry")


@pytest.mark.skip(reason="T-UR10b: legacy + Add overlay left the ledger; dialog journeys follow")
def test_new_planned_entry_lands_in_planned(world: World) -> None:
    account = world.account("Checking")
    category = world.category("Groceries")
    _open_overlay(world, "Planned")
    _pick(world, ledger.field_category, "Groceries")
    world.find(ledger.overlay_field(ledger.field_amount)).fill("33.00")
    _pick(world, ledger.field_account, "Checking")
    world.find(ledger.overlay_field(ledger.field_date)).fill(days_from_today(3))
    world.find(ledger.overlay_field(ledger.field_note)).fill("planned-entry")
    world.find(ledger.overlay_add_entry).click()

    found = world.wait_rows(
        "SELECT * FROM planned_transactions WHERE description = 'planned-entry'"
    )
    assert len(found) == 1
    assert (found[0]["amount"], found[0]["account_id"], found[0]["category_id"]) == (
        3300,
        account,
        category,
    )
    assert found[0]["promoted_to_txn_id"] is None
    assert world.audit_ops("planned_transaction", found[0]["id"]) == ["create"]
    assert world.scalar("SELECT COUNT(*) FROM transactions") == 0
    expect(world.find(ledger.slideover)).to_have_count(0)
    world.goto("/ledger?view=planned&date_from=2000-01-01&date_to=2099-12-31")
    expect(world.find(ledger.planned_row(found[0]["id"]))).to_contain_text("planned-entry")


@pytest.mark.skip(reason="T-UR10b: legacy + Add overlay left the ledger; dialog journeys follow")
def test_new_repeating_fixed_rule_lands_in_recurring(world: World) -> None:
    account = world.account("Checking")
    category = world.category("Rent")
    _open_overlay(world, "Repeats")
    _pick(world, ledger.field_category, "Rent")
    _pick(world, ledger.field_account, "Checking")
    world.find(ledger.amount_source_fixed).check()
    world.find(ledger.rule_amount).fill("1800.00")
    world.find(ledger.overlay_field(ledger.field_start)).fill(days_from_today(5))
    world.find(ledger.overlay_field(ledger.field_cadence)).select_option("quarterly")
    world.find(ledger.overlay_field(ledger.field_note)).fill("fixed-rule")
    world.find(ledger.add_rule).click()

    rule = world.wait_rows(
        "SELECT * FROM recurring_rules WHERE default_description = 'fixed-rule'"
    )[0]
    assert (rule["default_amount"], rule["cadence"], rule["account_id"]) == (
        180000,
        "quarterly",
        account,
    )
    assert (rule["category_id"], rule["amount_formula"], rule["active"]) == (category, None, 1)
    assert world.audit_ops("recurring_rule", rule["id"]) == ["create"]
    expect(world.find(ledger.slideover)).to_have_count(0)
    world.goto("/ledger?view=recurring")
    expect(world.find(ledger.recurring_row(rule["id"]))).to_contain_text("fixed-rule")


@pytest.mark.skip(reason="T-UR10b: legacy + Add overlay left the ledger; dialog journeys follow")
def test_new_repeating_formula_rule_derives_from_source(world: World) -> None:
    account = world.account("Checking")
    salary = world.category("Salary", "income")
    world.category("Savings", "expense")
    source_rule = world.rule(account, salary, "1000.00", "salary-rule")
    _open_overlay(world, "Repeats")
    _pick(world, ledger.field_category, "Savings")
    _pick(world, ledger.field_account, "Checking")
    world.find(ledger.amount_source_formula).dispatch_event(
        "click"
    )  # sr-only radio behind a styled label
    world.find(ledger.formula_pick_sources).click()
    world.find(ledger.formula_source("Salary")).check()
    world.find(ledger.formula_coefficient).fill("10")
    world.find(ledger.overlay_field(ledger.field_note)).fill("formula-rule")
    world.find(ledger.add_rule).click()

    rule = world.wait_rows(
        "SELECT * FROM recurring_rules WHERE default_description = 'formula-rule'"
    )[0]
    assert rule["amount_formula"] is not None
    assert f'"source_category_ids": [{salary}]' in rule["amount_formula"].replace('":[', '": [')
    assert source_rule != rule["id"]
    assert world.audit_ops("recurring_rule", rule["id"]) == ["create"]
    expect(world.find(ledger.slideover)).to_have_count(0)
    world.goto("/ledger?view=recurring")
    row = world.find(ledger.recurring_row(rule["id"]))
    expect(row).to_contain_text("formula-rule")
    expect(row).to_contain_text("100.00")  # 10% of the 1000.00 salary rule
