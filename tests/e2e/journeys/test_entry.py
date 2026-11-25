"""New-entry journeys: happened, planned, repeats (fixed and formula) (T-UT08b, T-UR09).

Each journey drives the new-entry dialog opened from the ledger's top bar through UI-map names
and asserts the row on screen plus the DB effect (the row, its amount in minor units, the audit).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.e2e.journeys._world import World, days_from_today
from tests.e2e.ui_actions import choose_account, choose_category, open_new_entry
from tests.ui_map import entries, ledger
from tests.ui_map.locator import label

pytestmark = pytest.mark.e2e

LEDGER_ALL_TIME = "/ledger?view=actual&date_from=2000-01-01&date_to=2099-12-31"


def _open_dialog(world: World, tab: str) -> None:
    world.goto(LEDGER_ALL_TIME)
    open_new_entry(world.page)
    if tab != "happened":
        tab_link = {"planned": entries.tab_planned, "repeats": entries.tab_repeats}[tab]
        world.find(tab_link).click()
        expect(world.find(tab_link)).to_have_attribute("aria-current", "page")


def test_new_happened_entry_lands_in_actual(world: World) -> None:
    account = world.account("Checking")
    category = world.category("Groceries")
    _open_dialog(world, "happened")
    choose_category(world.page, "Groceries")
    choose_account(world.page, "Checking")
    world.find(entries.hero_amount).fill("12.50")
    world.find(entries.field_note.inside(entries.dialog)).fill("happened-entry")
    world.find(entries.save).click()

    txn = world.wait_rows("SELECT * FROM transactions WHERE description = 'happened-entry'")
    assert len(txn) == 1
    assert (txn[0]["amount"], txn[0]["account_id"], txn[0]["category_id"]) == (
        1250,
        account,
        category,
    )
    assert txn[0]["deleted_at"] is None
    assert world.audit_ops("transaction", txn[0]["id"]) == ["create"]
    expect(world.find(entries.dialog)).to_have_count(0)  # saved: the dialog closes itself
    expect(world.find(ledger.row(txn[0]["id"]))).to_contain_text("happened-entry")


def test_new_planned_entry_lands_in_planned(world: World) -> None:
    account = world.account("Checking")
    category = world.category("Groceries")
    _open_dialog(world, "planned")
    choose_category(world.page, "Groceries")
    choose_account(world.page, "Checking")
    world.find(entries.hero_amount).fill("33.00")
    world.find(entries.field_due).fill(days_from_today(3))
    world.find(entries.field_note.inside(entries.dialog)).fill("planned-entry")
    world.find(entries.save).click()

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
    world.goto("/ledger?view=planned&date_from=2000-01-01&date_to=2099-12-31")
    expect(world.find(ledger.planned_row(found[0]["id"]))).to_contain_text("planned-entry")


def test_new_repeating_fixed_rule_lands_in_recurring(world: World) -> None:
    account = world.account("Checking")
    category = world.category("Rent")
    _open_dialog(world, "repeats")
    choose_category(world.page, "Rent")
    choose_account(world.page, "Checking")
    world.find(entries.amount_fixed).check(force=True)
    world.find(entries.hero_amount).fill("1800.00")
    world.find(entries.field_start).fill(days_from_today(5))
    world.find(entries.cadence_quarterly).check(force=True)
    world.find(entries.field_note.inside(entries.dialog)).fill("fixed-rule")
    world.find(entries.save).click()

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
    world.goto("/ledger?view=recurring")
    expect(world.find(ledger.recurring_row(rule["id"]))).to_contain_text("fixed-rule")


def test_new_repeating_formula_rule_derives_from_source(world: World) -> None:
    account = world.account("Checking")
    salary = world.category("Salary", "income")
    world.category("Savings", "expense")
    source_rule = world.rule(account, salary, "1000.00", "salary-rule")
    _open_dialog(world, "repeats")
    choose_category(world.page, "Savings")
    choose_account(world.page, "Checking")
    world.find(entries.amount_formula).check(force=True)
    world.find(entries.formula_pick).click()
    world.find(label("Salary", exact=True).inside(entries.formula_group)).check(force=True)
    world.find(entries.formula_percent).fill("10")
    world.find(entries.field_note.inside(entries.dialog)).fill("formula-rule")
    world.find(entries.save).click()

    rule = world.wait_rows(
        "SELECT * FROM recurring_rules WHERE default_description = 'formula-rule'"
    )[0]
    assert rule["amount_formula"] is not None
    assert f'"source_category_ids": [{salary}]' in rule["amount_formula"].replace('":[', '": [')
    assert source_rule != rule["id"]
    assert world.audit_ops("recurring_rule", rule["id"]) == ["create"]
    world.goto("/ledger?view=recurring")
    row = world.find(ledger.recurring_row(rule["id"]))
    expect(row).to_contain_text("formula-rule")
    expect(row).to_contain_text("100.00")  # 10% of the 1000.00 salary rule
