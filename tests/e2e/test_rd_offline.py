"""Offline save failure keeps the dialog and its typed input (T-UR25; ADR-0134 section 4).

App target only: the handoff mockup has no network to abort, so there is no
mockup variant. The dev dialog on ``/dev/shell`` posts to ``/dev/shell/dialog``;
Playwright aborts that request to simulate a request that gets no response.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e.mockup_target import Journey
from tests.ui_map import rd_shell as shell
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e

_POST = "**/dev/shell/dialog"


def _loc(journey: Journey, locator: Any) -> Any:
    return to_playwright(journey.page, locator)


def _abort_posts(route: Any) -> None:
    if route.request.method == "POST":
        route.abort()
    else:
        route.continue_()


def test_offline_save_keeps_input_shows_state_and_retry_saves(journey: Journey) -> None:
    if journey.target == "mockup":
        pytest.skip("the handoff mockup has no network to abort")
    page: Any = journey.page
    journey.goto("/dev/shell")
    _loc(journey, shell.dev_dialog_open).click()
    _loc(journey, shell.dev_dialog).wait_for(state="visible")
    _loc(journey, shell.dev_dialog_note).fill("rent split with Ola")

    page.route(_POST, _abort_posts)
    _loc(journey, shell.dev_dialog_save).click()

    _loc(journey, shell.offline_state).wait_for(state="visible")
    assert "You\u2019re offline" in _loc(journey, shell.offline_state).inner_text()
    assert _loc(journey, shell.dev_dialog).is_visible()
    assert _loc(journey, shell.dev_dialog_note).input_value() == "rent split with Ola"
    assert _loc(journey, shell.offline_state).evaluate("el => el === document.activeElement")
    assert _loc(journey, shell.offline_state).count() == 1

    page.unroute(_POST)
    _loc(journey, shell.offline_retry).click()

    _loc(journey, shell.dev_dialog).wait_for(state="detached")
    _loc(journey, shell.flash_saved).wait_for(state="visible")
    assert "rent split with Ola" in _loc(journey, shell.flash_saved).inner_text()


def test_second_failure_does_not_stack_offline_states(journey: Journey) -> None:
    if journey.target == "mockup":
        pytest.skip("the handoff mockup has no network to abort")
    page: Any = journey.page
    journey.goto("/dev/shell")
    _loc(journey, shell.dev_dialog_open).click()
    _loc(journey, shell.dev_dialog_note).fill("x")
    page.route(_POST, _abort_posts)
    _loc(journey, shell.dev_dialog_save).click()
    _loc(journey, shell.offline_retry).click()
    _loc(journey, shell.offline_state).wait_for(state="visible")
    assert _loc(journey, shell.offline_state).count() == 1
    assert _loc(journey, shell.dev_dialog_note).input_value() == "x"
