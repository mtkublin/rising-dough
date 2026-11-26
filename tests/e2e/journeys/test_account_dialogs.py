"""Account edit and delete dialogs through the row menu (T-UR08b, ADR-0107)."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.e2e.journeys._world import World
from tests.ui_map import accounts

pytestmark = pytest.mark.e2e


def _open_menu_item(world: World, account: int, item: str) -> None:
    world.goto("/accounts")
    world.find(accounts.row_menu(account)).click()
    world.find(accounts.menu_item(item).inside(accounts.row(account))).click()


def test_edit_renames_and_keeps_the_kind_read_only(world: World) -> None:
    account = world.account("Checking", opening="100.00")
    _open_menu_item(world, account, "edit")
    expect(world.find(accounts.edit_dialog("Checking"))).to_be_visible()
    expect(world.find(accounts.form_counts_as)).to_have_value("asset")
    expect(world.find(accounts.form_counts_as_toggle)).to_have_count(0)
    world.find(accounts.form_name).fill("Visa")
    world.find(accounts.save_account).click()

    expect(world.find(accounts.edit_dialog("Checking"))).to_have_count(0)
    row = world.wait_rows(
        "SELECT name, is_liability, credit_limit_minor FROM accounts WHERE id = ?", (account,)
    )[0]
    assert (row["name"], row["is_liability"], row["credit_limit_minor"]) == ("Visa", 0, None)
    assert world.audit_ops("account", account) == ["create", "update"]
    expect(world.find(accounts.row(account))).to_contain_text("Visa")


def test_delete_confirm_soft_deletes_an_unused_account(world: World) -> None:
    account = world.account("Spare", opening="0")
    _open_menu_item(world, account, "delete")
    expect(world.find(accounts.delete_dialog("Spare"))).to_be_visible()
    world.find(accounts.delete_confirm).click()

    expect(world.find(accounts.row(account))).to_have_count(0)
    expect(world.find(accounts.delete_dialog("Spare"))).to_have_count(0)
    row = world.wait_rows("SELECT deleted_at FROM accounts WHERE id = ?", (account,))[0]
    assert row["deleted_at"] is not None
    assert world.audit_ops("account", account) == ["create", "delete"]


def test_delete_is_blocked_by_a_transaction_and_writes_nothing(world: World) -> None:
    account = world.account("Used", opening="0")
    world.transaction(account, world.category(), "10.00", "blocker")
    _open_menu_item(world, account, "delete")
    expect(world.find(accounts.blocked_dialog("Used"))).to_be_visible()
    expect(world.find(accounts.blocked_dialog("Used"))).to_contain_text(
        "It still has 1 transaction"
    )
    world.find(accounts.blocked_ok).click()

    expect(world.find(accounts.blocked_dialog("Used"))).to_have_count(0)
    expect(world.find(accounts.row(account))).to_be_visible()
    assert world.scalar("SELECT deleted_at FROM accounts WHERE id = ?", (account,)) is None
    assert world.audit_ops("account", account) == ["create"]
