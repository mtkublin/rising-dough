"""Edit and delete with undo (T-UT08b): the row menu, the edit slide-over, and
restore from "Recently deleted". Screen result plus DB + audit effect."""

from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.e2e.journeys._world import World
from tests.ui_map import ledger
from tests.ui_map.locator import Locator

pytestmark = pytest.mark.e2e

LEDGER = "/ledger?view={view}&date_from=2000-01-01&date_to=2099-12-31"


def _menu_action(world: World, trigger: Locator, action: str) -> None:
    world.find(trigger).click()
    world.find(ledger.row_action(action)).click()


def test_edit_transaction_updates_row_and_db(world: World) -> None:
    txn = world.transaction(world.account(), world.category(), "12.34", "edit-me")
    world.goto(LEDGER.format(view="actual"))
    _menu_action(world, ledger.row_menu(txn), "Edit")
    expect(world.find(ledger.slideover)).to_be_visible()
    world.find(ledger.overlay_field(ledger.field_note)).fill("edited")
    # Amount last, then Save at once: a finished limit-preview GET from inside the
    # edit form would close the overlay (data-close-overlay-on-success matches any
    # successful request of a descendant), so do not wait between the two.
    world.find(ledger.overlay_field(ledger.field_amount)).fill("99.00")
    world.find(ledger.overlay_save).click()

    expect(world.find(ledger.slideover)).to_have_count(0)
    expect(world.find(ledger.row(txn))).to_contain_text("99.00")
    row = world.wait_rows("SELECT * FROM transactions WHERE id = ? AND amount = 9900", (txn,))[0]
    assert (row["description"], row["deleted_at"]) == ("edited", None)
    assert world.audit_ops("transaction", txn) == ["create", "update"]


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
