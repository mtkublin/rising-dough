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


@pytest.mark.skip(reason="T-UR09b: edit dialog not ported; the old slide-over sticks")
def test_edit_transaction_updates_row_and_db(world: World) -> None:
    txn = world.transaction(world.account(), world.category(), "12.34", "edit-me")
    world.goto(LEDGER.format(view="actual"))
    _menu_action(world, ledger.row_menu(txn), "edit")
    expect(world.find(ledger.slideover)).to_be_visible()
    world.find(ledger.overlay_field(ledger.field_note)).fill("edited")
    world.find(ledger.overlay_field(ledger.field_amount)).fill("99.00")
    world.find(ledger.overlay_save).click()

    expect(world.find(ledger.slideover)).to_have_count(0)
    expect(world.find(ledger.row(txn))).to_contain_text("99.00")
    row = world.wait_rows("SELECT * FROM transactions WHERE id = ? AND amount = 9900", (txn,))[0]
    assert (row["description"], row["deleted_at"]) == ("edited", None)
    assert world.audit_ops("transaction", txn) == ["create", "update"]


@pytest.mark.skip(reason="T-UR09b: edit dialog not ported; the old slide-over sticks")
def test_limit_preview_does_not_close_edit_slideover_before_save(world: World) -> None:
    txn = world.transaction(world.account(), world.category(), "12.34", "keep-open")
    world.goto(LEDGER.format(view="actual"))
    _menu_action(world, ledger.row_menu(txn), "edit")
    expect(world.find(ledger.slideover)).to_be_visible()
    amount = world.find(ledger.overlay_field(ledger.field_amount))
    # The slide-over is visible at swap time, but htmx wires the fragment's hx-trigger
    # listeners only after its settle step; keys typed earlier never fire the preview.
    world.page.wait_for_function(
        "el => el['htmx-internal-data'] !== undefined && !document.querySelector('.htmx-settling')",
        arg=amount.element_handle(),
    )
    amount.fill("")
    with world.page.expect_response(lambda r: "/transactions/_limit_preview" in r.url):
        amount.press_sequentially("45.67")  # real keystrokes fire the keyup preview trigger
    world.settle()
    expect(amount).to_have_value("45.67")
    expect(world.find(ledger.slideover)).to_be_visible()
    assert world.rows("SELECT 1 FROM transactions WHERE id = ? AND amount = 1234", (txn,))

    world.find(ledger.overlay_save).click()
    expect(world.find(ledger.slideover)).to_have_count(0)
    row = world.wait_rows("SELECT * FROM transactions WHERE id = ? AND amount = 4567", (txn,))[0]
    assert row["deleted_at"] is None


def test_delete_transaction_then_undo_from_recently_deleted(world: World) -> None:
    txn = world.transaction(world.account(), world.category(), "7.00", "delete-me")
    world.goto(LEDGER.format(view="actual"))
    _menu_action(world, ledger.row_menu(txn), "delete")  # native confirm is accepted

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


@pytest.mark.skip(reason="T-UR10a: planned and recurring rows keep the old kebab")
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
