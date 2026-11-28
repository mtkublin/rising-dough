"""A failing save shows its message once (DUPERR, T-UR16 sweep finding 3, ADR-0143 amendment).

While a dialog is open the error shows in the dialog (in context) and no toast repeats it, whether
the server sent the flash partial or an error toast; a page-level action outside a dialog (a row
delete) keeps its single message.
"""

from __future__ import annotations

import json

import pytest
from playwright.sync_api import Route, expect

from tests.e2e.journeys._world import World
from tests.e2e.ui_actions import (
    choose_account,
    choose_category,
    fill_stable,
    open_new_entry,
)
from tests.ui_map import entries, ledger, rd_shell
from tests.ui_map.locator import role

pytestmark = pytest.mark.e2e

LEDGER_ALL_TIME = "/ledger?view=actual&date_from=2000-01-01&date_to=2099-12-31"
TOASTS = role("status").inside(rd_shell.toast_root)
MESSAGES = {
    404: "That item was not found. It may have been removed.",
    409: "That item changed in the meantime. Reload and try again.",
    500: "Something went wrong on our side. Try again.",
}
SERVER_FLASH = (  # the shape of fragments/flash/error.html with region="flash-region"
    '<div id="flash-region" role="status" aria-live="polite" hx-swap-oob="true">'
    '<div class="rd-flash rd-flash--error" role="alert"><span>▲ {msg}</span></div></div>'
)
TOAST_TEXT = "Could not archive: still in use"


def _open_filled_entry(world: World) -> None:
    world.account("Checking")
    world.category("Groceries")
    world.goto(LEDGER_ALL_TIME)
    open_new_entry(world.page)
    choose_category(world.page, "Groceries")
    choose_account(world.page, "Checking")
    fill_stable(world.find(entries.hero_amount), "12.50")


@pytest.mark.parametrize("server_flash", [False, True], ids=["plain-body", "server-flash"])
@pytest.mark.parametrize("status", [404, 409, 500])
def test_failed_new_entry_save_shows_one_message_in_the_dialog(
    world: World, status: int, server_flash: bool
) -> None:
    def fail(route: Route) -> None:
        body = SERVER_FLASH.format(msg=MESSAGES[status]) if server_flash else "nope"
        route.fulfill(status=status, content_type="text/html", body=body)

    _open_filled_entry(world)
    world.page.route("**/transactions", fail)
    world.find(entries.save).click()

    expect(world.find(rd_shell.in_dialog_flash_box)).to_contain_text(MESSAGES[status])
    expect(world.find(entries.dialog)).to_be_visible()
    world.page.wait_for_timeout(300)  # a toast would have been appended by now
    expect(world.find(TOASTS)).to_have_count(0)
    expect(world.page.get_by_text(MESSAGES[status])).to_have_count(1)
    assert world.rows("SELECT 1 FROM transactions") == []


def test_error_toast_from_the_server_goes_into_the_open_dialog(world: World) -> None:
    def blocked(route: Route) -> None:
        trigger = {"toast": {"variant": "error", "message": TOAST_TEXT}}
        route.fulfill(
            status=422,
            body=TOAST_TEXT,
            headers={"HX-Trigger": json.dumps(trigger), "HX-Reswap": "none"},
        )

    _open_filled_entry(world)
    world.page.route("**/transactions", blocked)
    world.find(entries.save).click()

    expect(world.find(rd_shell.in_dialog_flash_box)).to_contain_text(TOAST_TEXT)
    world.page.wait_for_timeout(300)
    expect(world.find(TOASTS)).to_have_count(0)
    expect(world.page.get_by_text(TOAST_TEXT)).to_have_count(1)


def test_failed_row_delete_outside_a_dialog_shows_one_message(world: World) -> None:
    txn = world.transaction(world.account(), world.category(), "7.00", "delete-me")
    world.goto(LEDGER_ALL_TIME)
    world.page.route(f"**/transactions/{txn}/delete", lambda r: r.fulfill(status=500, body="nope"))
    world.find(ledger.row_menu(txn)).click()
    world.find(ledger.row_action("delete")).click()

    expect(world.find(rd_shell.flash_region)).to_contain_text(MESSAGES[500])
    expect(world.page.get_by_text(MESSAGES[500])).to_have_count(1)
    assert world.rows("SELECT 1 FROM transactions WHERE id = ? AND deleted_at IS NULL", (txn,))
