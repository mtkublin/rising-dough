"""Today journey on either target (T-UT09; ADR-0106).

``--target=app`` (default) loads the live Today page; ``--target=mockup``
runs the same names against ``pages/today.html`` and also clicks through to
the promote overlay (the app promotes inline, so that step is mockup-only).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e import mockup_target
from tests.e2e.mockup_target import Journey
from tests.ui_map.locator import role, to_playwright

pytestmark = pytest.mark.e2e

# Fixtures re-exported until the conftest registers the plugin.
target = mockup_target.target
mockup_base_url = mockup_target.mockup_base_url
journey = mockup_target.journey

PROMOTE_DIALOG_HEADING = role("heading", "promote to actual")


def test_today_shows_hero_and_upcoming(journey: Journey) -> None:
    today = journey.ui("today")
    journey.goto("/today")
    to_playwright(journey.page, today.heading).wait_for(state="visible")
    to_playwright(journey.page, today.upcoming).wait_for(state="visible")


def test_today_promote_opens_overlay(journey: Journey) -> None:
    if journey.target != "mockup":
        pytest.skip("app promotes inline; the overlay click-through is a handoff flow")
    today = journey.ui("today")
    journey.goto("/today")
    page: Any = journey.page
    to_playwright(page, today.promote).first.click()
    page.wait_for_url("**/pages/overlays/promote--*.html")
    to_playwright(page, PROMOTE_DIALOG_HEADING).first.wait_for(state="visible")
