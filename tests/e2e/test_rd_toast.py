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
_toast_undo_form = by_id("toast-root")


def _loc(journey: Journey, locator: Any) -> Any:
    return to_playwright(journey.page, locator)


def test_hx_trigger_toast_shows_message_and_undo_link(journey: Journey) -> None:
    if journey.target == "mockup":
        pytest.skip("the handoff mockup has no server to send HX-Trigger")
    journey.goto("/dev/shell")
    _loc(journey, _dev_toast_button).click()

    toast = _loc(journey, shell.toast_root).get_by_role("status")
    toast.wait_for(state="visible")
    assert "Dev toast saved" in toast.inner_text()
    form = _loc(journey, _toast_undo_form).locator("form")
    assert form.get_attribute("action") == "/dev/shell/toast/undo"
    assert form.get_by_role("button", name="undo").is_visible()


def test_toast_leaves_on_its_own(journey: Journey) -> None:
    if journey.target == "mockup":
        pytest.skip("the handoff mockup has no server to send HX-Trigger")
    journey.goto("/dev/shell")
    _loc(journey, _dev_toast_button).click()
    toast = _loc(journey, shell.toast_root).get_by_role("status")
    toast.wait_for(state="visible")
    toast.wait_for(state="detached", timeout=12000)
