"""Edit and delete with undo (T-UT08b, T-UR09b): the row menu, the edit dialog, and
restore from "Recently deleted". Screen result plus DB + audit effect."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.e2e.journeys._world import World
from tests.ui_map import entries, ledger
from tests.ui_map.locator import Locator

pytestmark = pytest.mark.e2e

LEDGER = "/ledger?view={view}&date_from=2000-01-01&date_to=2099-12-31"


def _menu_action(world: World, trigger: Locator, action: str) -> None:
    world.find(trigger).click()
    world.find(ledger.row_action(action)).click()


def _open_edit(world: World, txn: int) -> None:
    """Open the edit dialog through its own URL: the shell page asks for it on load (T-UR09b)."""
    world.goto(f"/transactions/{txn}/edit")
    expect(world.find(entries.edit_dialog)).to_be_visible()


def test_edit_transaction_updates_row_and_db(world: World) -> None:
    txn = world.transaction(world.account(), world.category(), "12.34", "edit-me")
    _open_edit(world, txn)
    expect(world.find(entries.edit_amount)).to_have_value("12.34")
    world.find(entries.field_note).fill("edited")
    world.find(entries.edit_amount).fill("99.00")
    world.find(entries.edit_save).click()

    expect(world.find(entries.edit_dialog)).to_have_count(0)
    row = world.wait_rows("SELECT * FROM transactions WHERE id = ? AND amount = 9900", (txn,))[0]
    assert (row["description"], row["deleted_at"]) == ("edited", None)
    assert world.audit_ops("transaction", txn) == ["create", "update"]
    world.goto(LEDGER.format(view="actual"))
    expect(world.find(ledger.row(txn))).to_contain_text("99.00")


def test_a_bad_edit_keeps_the_dialog_open_with_the_error(world: World) -> None:
    txn = world.transaction(world.account(), world.category(), "12.34", "bad-edit")
    _open_edit(world, txn)
    world.find(entries.edit_amount).fill("0")
    world.find(entries.edit_save).click()

    expect(world.find(entries.summary)).to_be_visible()
    expect(world.find(entries.edit_dialog)).to_be_visible()
    assert world.rows("SELECT 1 FROM transactions WHERE id = ? AND amount = 1234", (txn,))
    assert world.audit_ops("transaction", txn) == ["create"]


def test_limit_preview_does_not_close_edit_dialog_before_save(world: World) -> None:
    txn = world.transaction(world.account(), world.category(), "12.34", "keep-open")
    _open_edit(world, txn)
    amount = world.find(entries.edit_amount)
    # The dialog is visible at swap time, but htmx wires the fragment's hx-trigger
    # listeners only after its settle step; keys typed earlier never fire the preview.
    world.page.wait_for_function(
        "el => el['htmx-internal-data'] !== undefined && !document.querySelector('.htmx-settling')",
        arg=world.find(entries.credit_line).element_handle(),
    )
    amount.fill("")
    with world.page.expect_response(lambda r: "/transactions/_limit_preview" in r.url):
        amount.press_sequentially("45.67")  # real keystrokes fire the keyup preview trigger
    world.settle()
    expect(amount).to_have_value("45.67")
    expect(world.find(entries.edit_dialog)).to_be_visible()
    assert world.rows("SELECT 1 FROM transactions WHERE id = ? AND amount = 1234", (txn,))

    world.find(entries.edit_save).click()
    expect(world.find(entries.edit_dialog)).to_have_count(0)
    row = world.wait_rows("SELECT * FROM transactions WHERE id = ? AND amount = 4567", (txn,))[0]
    assert row["deleted_at"] is None


def test_delete_transaction_then_undo_from_recently_deleted(world: World) -> None:
    txn = world.transaction(world.account(), world.category(), "7.00", "delete-me")
    world.goto(LEDGER.format(view="actual"))
    _menu_action(world, ledger.row_menu(txn), "Delete")  # native confirm is accepted

    expect(world.find(ledger.row(txn))).to_have_count(0)
    world.wait_rows("SELECT 1 FROM transactions WHERE id = ? AND deleted_at IS NOT NULL", (txn,))
    assert world.audit_ops("transaction", txn) == ["create", "delete"]

    world.find(ledger.recently_deleted_link).click()
    world.settle()
    expect(world.find(ledger.recently_deleted_heading)).to_be_visible()
    expect(world.find(ledger.deleted_row("txn", txn))).to_contain_text("delete-me")
    world.find(ledger.restore("txn", txn)).click()

    world.wait_rows("SELECT 1 FROM transactions WHERE id = ? AND deleted_at IS NULL", (txn,))
    assert world.audit_ops("transaction", txn) == ["create", "delete", "undelete"]
    world.goto(LEDGER.format(view="actual"))
    expect(world.find(ledger.row(txn))).to_contain_text("delete-me")


def test_delete_planned_entry_then_undo(world: World) -> None:
    planned = world.planned(world.account(), world.category(), "25.00", "planned-delete-me")
    world.goto(LEDGER.format(view="planned"))
    _menu_action(world, ledger.planned_menu(planned), "Delete")

    expect(world.find(ledger.planned_row(planned))).to_have_count(0)
    world.wait_rows(
        "SELECT 1 FROM planned_transactions WHERE id = ? AND deleted_at IS NOT NULL", (planned,)
    )
    world.find(ledger.recently_deleted_link).click()
    world.settle()
    world.find(ledger.restore("planned", planned)).click()

    world.wait_rows(
        "SELECT 1 FROM planned_transactions WHERE id = ? AND deleted_at IS NULL", (planned,)
    )
    assert world.audit_ops("planned_transaction", planned) == ["create", "delete", "undelete"]
    world.goto(LEDGER.format(view="planned"))
    expect(world.find(ledger.planned_row(planned))).to_contain_text("planned-delete-me")
