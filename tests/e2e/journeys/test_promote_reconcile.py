"""Promote (planned and recurring) and reconcile (asset and liability) (T-UT08b)."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.e2e.journeys._world import World, days_from_today
from tests.ui_map import accounts, ledger

pytestmark = pytest.mark.e2e

LEDGER = "/ledger?view={view}&date_from=2000-01-01&date_to=2099-12-31"


@pytest.mark.skip(reason="T-UR10a: planned and recurring rows keep the old kebab")
def test_promote_planned_entry_creates_the_transaction(world: World) -> None:
    account = world.account()
    planned = world.planned(account, world.category(), "25.00", "promote-planned")
    world.goto(LEDGER.format(view="planned"))
    world.find(ledger.planned_promote(planned)).click()
    expect(world.find(ledger.slideover)).to_be_visible()
    world.find(ledger.overlay_promote).click()

    expect(world.find(ledger.slideover)).to_have_count(0)
    txn = world.wait_rows(
        "SELECT * FROM transactions WHERE promoted_from_planned_id = ?", (planned,)
    )[0]
    assert (txn["amount"], txn["account_id"], txn["description"]) == (
        2500,
        account,
        "promote-planned",
    )
    assert (
        world.scalar("SELECT promoted_to_txn_id FROM planned_transactions WHERE id = ?", (planned,))
        == txn["id"]
    )
    assert world.audit_ops("transaction", txn["id"]) == ["create"]
    world.goto(LEDGER.format(view="actual"))
    expect(world.find(ledger.row(txn["id"]))).to_contain_text("promote-planned")


@pytest.mark.skip(reason="T-UR10a: planned and recurring rows keep the old kebab")
def test_promote_recurring_rule_advances_it(world: World) -> None:
    account = world.account()
    start = days_from_today(1)
    rule = world.rule(account, world.category("Rent"), "800.00", "promote-rule", start=start)
    world.goto(LEDGER.format(view="recurring"))
    world.find(ledger.recurring_menu(rule)).click()
    world.find(ledger.row_action("Promote")).click()
    expect(world.find(ledger.promote_dialog)).to_be_visible()
    world.find(ledger.overlay_promote).click()

    expect(world.find(ledger.slideover)).to_have_count(0)
    txn = world.wait_rows(
        "SELECT * FROM transactions WHERE promoted_from_recurring_rule_id = ?", (rule,)
    )[0]
    assert (txn["amount"], txn["promoted_from_recurring_date"]) == (80000, start)
    after = world.rows(
        "SELECT next_due, last_promoted_date FROM recurring_rules WHERE id = ?", (rule,)
    )[0]
    assert after["last_promoted_date"] == start
    assert after["next_due"] > start
    world.goto(LEDGER.format(view="actual"))
    expect(world.find(ledger.row(txn["id"]))).to_contain_text("promote-rule")


@pytest.mark.skip(reason="T-UR08b: reconcile dialog not ported yet")
def test_reconcile_asset_records_an_adjustment(world: World) -> None:
    account = world.account("Checking", opening="100.00")
    world.goto("/accounts")
    world.find(accounts.reconcile_button(account)).click()
    expect(world.find(accounts.reconcile_dialog)).to_be_visible()
    world.find(accounts.reconcile_actual).fill("70.00")
    world.find(accounts.reconcile_record).click()

    expect(world.find(accounts.reconcile_dialog)).to_have_count(0)
    adj = world.wait_rows(
        "SELECT t.* FROM transactions t JOIN categories c ON c.id = t.category_id "
        "WHERE t.account_id = ? AND c.direction = 'adjustment'",
        (account,),
    )[0]
    assert adj["amount"] == -3000
    assert world.audit_ops("transaction", adj["id"]) == ["create"]
    expect(world.find(accounts.row(account))).to_contain_text("70.00")


@pytest.mark.skip(reason="T-UR08b: reconcile dialog not ported yet")
def test_reconcile_liability_asks_for_available_credit(world: World) -> None:
    card = world.account("Visa", opening="-1234.56", liability=True, credit_limit="5000.00")
    world.goto("/accounts")
    world.find(accounts.reconcile_button(card)).click()
    expect(world.find(accounts.reconcile_available)).to_have_value("3765.44")
    world.find(accounts.reconcile_available).fill("4000.00")
    world.find(accounts.reconcile_record).click()

    expect(world.find(accounts.reconcile_dialog)).to_have_count(0)
    adj = world.wait_rows(
        "SELECT t.* FROM transactions t JOIN categories c ON c.id = t.category_id "
        "WHERE t.account_id = ? AND c.direction = 'adjustment'",
        (card,),
    )[0]
    assert adj["amount"] == 23456
    expect(world.find(accounts.row(card))).to_contain_text("Available 4,000.00")
