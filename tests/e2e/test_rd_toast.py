"""HX-Trigger toast renders into #toast-root and closes (T-UR02; ADR-0143).

App target only: the dev button on ``/dev/shell`` posts to ``/dev/shell/toast``,
which answers with ``HX-Trigger: {"toast": {...}}``.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e.mockup_target import Journey
from tests.ui_map import rd_shell as shell
from tests.ui_map.locator import by_id, role, to_playwright

pytestmark = pytest.mark.e2e

_dev_toast_button = role("button", "show dev toast")
_toast_any = role("status").inside(shell.toast_root)
_flash_assertive = by_id("flash-region-assertive")
_fail_409 = role("button", "fail with 409")
_fail_404 = role("button", "fail with plain 404")
_fail_500 = role("button", "fail with 500")
_toast_undo = role("button", "undo").inside(shell.toast_root)


def _loc(journey: Journey, locator: Any) -> Any:
    return to_playwright(journey.page, locator)


def test_hx_trigger_toast_shows_message_and_undo_link(journey: Journey) -> None:
    if journey.target == "mockup":
        pytest.skip("the handoff mockup has no server to send HX-Trigger")
    journey.goto("/dev/shell")
    _loc(journey, _dev_toast_button).click()

    _loc(journey, shell.toast_root).get_by_text("Dev toast saved").wait_for(state="visible")
    undo = _loc(journey, _toast_undo)
    undo.wait_for(state="visible")
    assert undo.evaluate("el => el.form.getAttribute('action')") == "/dev/shell/toast/undo"


def test_toast_leaves_on_its_own(journey: Journey) -> None:
    if journey.target == "mockup":
        pytest.skip("the handoff mockup has no server to send HX-Trigger")
    journey.goto("/dev/shell")
    _loc(journey, _dev_toast_button).click()
    toast = _loc(journey, _toast_any)
    toast.wait_for(state="visible")
    toast.wait_for(state="detached", timeout=12000)


def test_conflict_response_flashes_in_the_new_shell(journey: Journey) -> None:
    if journey.target == "mockup":
        pytest.skip("the handoff mockup has no server to answer an error")
    journey.goto("/dev/shell")
    _loc(journey, _fail_409).click()
    flash = _loc(journey, shell.flash_region).get_by_text("Dev conflict: that row is protected")
    flash.wait_for(state="visible")


def test_server_error_flashes_in_the_new_shell(journey: Journey) -> None:
    if journey.target == "mockup":
        pytest.skip("the handoff mockup has no server to answer an error")
    journey.goto("/dev/shell")
    _loc(journey, _fail_500).click()
    flash = _loc(journey, _flash_assertive).get_by_text("Something went wrong on our side.")
    flash.wait_for(state="visible")


def test_repeated_errors_keep_the_region_and_show_the_latest(journey: Journey) -> None:
    if journey.target == "mockup":
        pytest.skip("the handoff mockup has no server to answer an error")
    journey.goto("/dev/shell")
    _loc(journey, _fail_500).click()
    region = _loc(journey, _flash_assertive)
    region.get_by_text("Something went wrong on our side.").wait_for(state="visible")
    _loc(journey, _fail_500).click()
    region.get_by_text("Something went wrong on our side.").wait_for(state="visible")
    assert region.get_attribute("role") == "alert"
    assert region.get_attribute("aria-live") == "assertive"
    assert "rd-flash-region" in (region.get_attribute("class") or "").split()
    _loc(journey, _fail_409).click()
    _loc(journey, shell.flash_region).get_by_text("Dev conflict: that row is protected").wait_for(
        state="visible"
    )
    assert region.get_attribute("class") == "rd-flash-region"


def test_plain_text_404_still_shows_a_visible_message(journey: Journey) -> None:
    if journey.target == "mockup":
        pytest.skip("the handoff mockup has no server to answer an error")
    journey.goto("/dev/shell")
    _loc(journey, _fail_404).click()
    _loc(journey, _flash_assertive).get_by_text(
        "That item was not found. It may have been removed."
    ).wait_for(state="visible")
