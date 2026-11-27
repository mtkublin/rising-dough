"""prefers-reduced-motion: reduce leaves no running transition or animation (T-UR97, T-UR16).

``rd/css/base.css`` caps ``animation-duration`` and ``transition-duration`` at 1 ms on every
element under ``@media (prefers-reduced-motion: reduce)``. The checks read the computed style on
the dialog, the flash and the toast, with the media query forced on and, as a control, off.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e.mockup_target import Journey
from tests.e2e.ui_actions import open_new_entry
from tests.ui_map import entries, rd_shell as shell
from tests.ui_map.locator import role, to_playwright

pytestmark = pytest.mark.e2e

_MAX_SECONDS = 0.01
_dev_toast_button = role("button", "show dev toast")
_fail_409 = role("button", "fail with 409")

_DURATIONS = """el => {
  const nodes = [el, ...el.querySelectorAll('*')];
  const one = (x) => parseFloat(x) * (x.trim().endsWith('ms') ? 0.001 : 1);
  const secs = (v) => v.split(',').map(one);
  return nodes.flatMap((n) => {
    const s = getComputedStyle(n);
    return [...secs(s.transitionDuration), ...secs(s.animationDuration)];
  });
}"""


def _loc(journey: Journey, locator: Any) -> Any:
    return to_playwright(journey.page, locator)


def _longest(journey: Journey, locator: Any) -> float:
    durations = _loc(journey, locator).evaluate(_DURATIONS)
    assert durations
    return float(max(durations))


def test_media_query_matches_when_reduced(journey: Journey) -> None:
    journey.page.emulate_media(reduced_motion="reduce")
    journey.goto("/dev/shell")
    assert journey.page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches") is True
    journey.page.emulate_media(reduced_motion="no-preference")
    assert journey.page.evaluate("matchMedia('(prefers-reduced-motion: reduce)').matches") is False


def test_dialog_has_no_long_motion_when_reduced(journey: Journey) -> None:
    if journey.target == "mockup":
        pytest.skip("app-only: the dialog comes from the server")
    journey.page.emulate_media(reduced_motion="reduce")
    journey.goto("/ledger")
    open_new_entry(journey.page)
    assert _longest(journey, entries.dialog) <= _MAX_SECONDS
    assert _longest(journey, shell.modal_root) <= _MAX_SECONDS


def test_toast_has_no_long_motion_when_reduced(journey: Journey) -> None:
    if journey.target == "mockup":
        pytest.skip("app-only: the toast needs an HX-Trigger from the server")
    journey.page.emulate_media(reduced_motion="reduce")
    journey.goto("/dev/shell")
    _loc(journey, _dev_toast_button).click()
    toast = _loc(journey, shell.toast_root).get_by_text("PLN deleted")
    toast.wait_for(state="visible")
    assert _longest(journey, shell.toast_root) <= _MAX_SECONDS


def test_flash_has_no_long_motion_when_reduced(journey: Journey) -> None:
    if journey.target == "mockup":
        pytest.skip("app-only: the flash needs an error answer from the server")
    journey.page.emulate_media(reduced_motion="reduce")
    journey.goto("/dev/shell")
    _loc(journey, _fail_409).click()
    _loc(journey, shell.flash_region).get_by_text("Dev conflict: that row is protected").wait_for(
        state="visible"
    )
    assert _longest(journey, shell.flash_region) <= _MAX_SECONDS
