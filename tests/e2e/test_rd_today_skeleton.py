"""Today's upcoming list: skeleton while a range request runs, list restored when it fails.

App target only (T-UR00b, F5): ``static/rd/js/skeleton.js`` swaps the list for the skeleton on
request start; an error answer that swaps nothing (app-toast.js) must put the list back.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e.mockup_target import Journey
from tests.ui_map.locator import by_id, role, to_playwright

pytestmark = pytest.mark.e2e

_range_30 = role("button", "30 days")
_range_all = role("button", "all").inside(by_id("upcoming"))
_list = by_id("upcoming-list")
_section = by_id("upcoming")


def _loc(journey: Journey, locator: Any) -> Any:
    return to_playwright(journey.page, locator)


def test_failed_range_request_restores_the_list(journey: Journey) -> None:
    if journey.target == "mockup":
        pytest.skip("the handoff mockup has no server to answer an error")
    journey.goto("/today")
    before = _loc(journey, _list).inner_text()

    def fail(route: Any) -> None:
        route.fulfill(status=500, body="boom")

    journey.page.route("**/today/upcoming?window=all", fail)
    _loc(journey, _range_all).click()
    journey.page.wait_for_selector("#flash-region .rd-flash--error")
    assert _loc(journey, _list).inner_text() == before  # the skeleton has no text
    assert _loc(journey, _section).get_attribute("aria-busy") is None


def test_successful_range_request_clears_busy(journey: Journey) -> None:
    if journey.target == "mockup":
        pytest.skip("the handoff mockup has no server")
    journey.goto("/today")
    _loc(journey, _range_30).click()
    journey.page.wait_for_load_state("networkidle")
    assert _loc(journey, _section).get_attribute("aria-busy") is None
