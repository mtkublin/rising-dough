"""Shared dialog shell, opened from the dev row menu on /dev/shell (T-UR04e, ADR-0107 section 2).

App target only: the dev menu and its routes do not exist in the handoff. Each variant
opens from a row-menu item (HTMX get into ``#modal-root``), closes on Escape and on the
close button, and returns focus to the menu trigger; the 422 shows a ▲ line under each field and
the phone sheet docks at the bottom of a 375 px viewport.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e.mockup_target import Journey
from tests.ui_map import rd_dialogs as d, rd_fragments as f, rd_shell as shell
from tests.ui_map.locator import Locator, by_id, role, to_playwright

pytestmark = pytest.mark.e2e


def _loc(journey: Journey, locator: Locator) -> Any:
    return to_playwright(journey.page, locator)


def _open(journey: Journey, item: str, dialog: Locator) -> Any:
    if journey.target == "mockup":
        pytest.skip("the handoff mockup has no dev row menu")
    journey.goto("/dev/shell")
    _loc(journey, d.dev_menu_button).click()
    _loc(journey, f.row_menu_item(item)).click()
    target = _loc(journey, dialog)
    target.wait_for(state="visible")
    return target


@pytest.mark.parametrize(
    ("item", "dialog"),
    [
        ("standard", d.dev_standard),
        ("blocked", d.dev_blocked),
        ("delete", d.dev_confirm),
    ],
)
def test_variant_opens_from_the_menu_and_escape_closes_it(
    journey: Journey, item: str, dialog: Locator
) -> None:
    _open(journey, item, dialog)
    assert _loc(journey, dialog).evaluate("el => el.open") is True
    journey.page.keyboard.press("Escape")
    _loc(journey, dialog).wait_for(state="hidden")
    assert _loc(journey, d.dev_menu_button).evaluate("el => el === document.activeElement")


def test_close_button_closes_and_focus_returns_to_the_trigger(journey: Journey) -> None:
    _open(journey, "standard", d.dev_standard)
    _loc(journey, d.close_button(d.dev_standard)).click()
    _loc(journey, d.dev_standard).wait_for(state="hidden")
    assert _loc(journey, d.dev_menu_button).evaluate("el => el === document.activeElement")


def test_cancel_and_ok_actions_close(journey: Journey) -> None:
    _open(journey, "delete", d.dev_confirm)
    _loc(journey, d.action(d.dev_confirm, "cancel")).click()
    _loc(journey, d.dev_confirm).wait_for(state="hidden")
    _loc(journey, d.dev_menu_button).click()
    _loc(journey, f.row_menu_item("blocked")).click()
    _loc(journey, d.dev_blocked).wait_for(state="visible")
    _loc(journey, d.action(d.dev_blocked, "[ ok ]")).click()
    _loc(journey, d.dev_blocked).wait_for(state="hidden")


def test_invalid_variant_shows_each_field_error_and_no_summary_box(journey: Journey) -> None:
    dialog = d.dialog("new account")
    _open(journey, "invalid", dialog)
    amount = _loc(journey, d.field_error(dialog, "amount"))
    amount.wait_for(state="visible")
    assert " ".join(amount.inner_text().split()) == "▲ Enter an amount above 0.00"
    name = _loc(journey, d.field_error(dialog, "name"))
    assert " ".join(name.inner_text().split()) == "▲ Name is required"
    assert _loc(journey, by_id("error-summary")).count() == 0


def test_submitting_the_standard_form_shows_the_422_field_errors(journey: Journey) -> None:
    _open(journey, "standard", d.dev_standard)
    _loc(journey, d.action(d.dev_standard, "[ create account ]")).click()
    dialog = d.dialog("new account")
    amount = _loc(journey, d.field_error(dialog, "amount"))
    amount.wait_for(state="visible")
    assert " ".join(amount.inner_text().split()) == "▲ Enter an amount above 0.00"
    name = _loc(journey, d.field_error(dialog, "name"))
    assert " ".join(name.inner_text().split()) == "▲ Name is required"
    assert _loc(journey, by_id("error-summary")).count() == 0


def test_phone_sheet_docks_to_the_bottom_at_375(journey: Journey) -> None:
    if journey.target == "mockup":
        pytest.skip("the handoff mockup has no dev row menu")
    journey.page.set_viewport_size({"width": 375, "height": 812})
    _open(journey, "sheet", d.dev_sheet)
    _loc(journey, d.dev_sheet).evaluate(
        "el => Promise.all(el.getAnimations().map(a => a.finished))"
    )
    box = _loc(journey, d.dev_sheet).bounding_box()
    assert box is not None
    assert box["x"] == 0
    assert box["width"] == 375
    assert box["y"] + box["height"] == pytest.approx(812, abs=1)
    journey.page.keyboard.press("Escape")
    _loc(journey, d.dev_sheet).wait_for(state="hidden")


def test_phone_only_item_is_hidden_on_desktop(journey: Journey) -> None:
    if journey.target == "mockup":
        pytest.skip("the handoff mockup has no dev row menu")
    journey.goto("/dev/shell")
    _loc(journey, d.dev_menu_button).click()
    _loc(journey, f.row_menu_item("standard")).wait_for(state="visible")
    assert _loc(journey, f.row_menu_item("sheet")).is_visible() is False


def test_error_flash_shows_above_an_open_modal_dialog(journey: Journey) -> None:
    """A 500 from inside a modal dialog flashes above the backdrop (T-UR02c, ADR-0143)."""
    if journey.target == "mockup":
        pytest.skip("the handoff mockup has no server to answer an error")
    journey.goto("/dev/shell")
    _loc(journey, shell.dev_dialog_open).click()
    _loc(journey, shell.dev_dialog).wait_for(state="visible")
    _loc(journey, role("button", "fail with 500").inside(shell.dev_dialog)).click()

    flash = _loc(journey, role("alert").inside(shell.dev_dialog)).get_by_text(
        "Couldn\u2019t save. Your changes are still in the form."
    )
    flash.wait_for(state="visible")
    assert "▲" in flash.inner_text()
    on_top = flash.evaluate(
        """el => {
            const r = el.getBoundingClientRect();
            const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
            return !!hit && el.closest('.rd-flash').contains(hit);
        }"""
    )
    assert on_top is True
    journey.page.keyboard.press("Escape")
    _loc(journey, shell.dev_dialog).wait_for(state="hidden")


def test_reopened_dialog_starts_without_the_old_flash(journey: Journey) -> None:
    """The in-dialog flash is single, cleared on reopen, dropped when closed (T-UR02c)."""
    if journey.target == "mockup":
        pytest.skip("the handoff mockup has no server to answer an error")
    journey.goto("/dev/shell")
    _loc(journey, shell.dev_dialog_open).click()
    _loc(journey, shell.dev_dialog).wait_for(state="visible")
    fail = _loc(journey, role("button", "fail with 500").inside(shell.dev_dialog))
    fail.click()
    _loc(journey, shell.in_dialog_flash_box).wait_for(state="visible")
    assert _loc(journey, shell.in_dialog_flash).count() == 1

    # Close and reopen the same element (a static dialog is not replaced by #modal-root).
    _loc(journey, shell.dev_dialog).evaluate("d => { d.close(); d.showModal(); }")
    _loc(journey, shell.in_dialog_flash).wait_for(state="detached")

    fail.click()
    _loc(journey, shell.in_dialog_flash_box).wait_for(state="visible")
    assert _loc(journey, shell.in_dialog_flash).count() == 1

    # A closed dialog's region goes with the next request of any kind.
    _loc(journey, shell.dev_dialog).evaluate("d => { d.close(); htmx.ajax('GET', '/healthz'); }")
    _loc(journey, shell.in_dialog_flash).wait_for(state="detached")
