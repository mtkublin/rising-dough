"""Today journey on either target (T-UT09; ADR-0106).

``--target=app`` (default) loads the live Today page; ``--target=mockup``
runs the same names against ``pages/today.html`` and also clicks through to
the promote overlay (the app's promote dialog is ported with T-UR07b, so that
step is mockup-only until then).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e.mockup_target import Journey
from tests.ui_map.locator import role, to_playwright

pytestmark = pytest.mark.e2e

PROMOTE_DIALOG_HEADING = role("heading", "promote to actual")


def test_today_shows_hero_and_upcoming(journey: Journey) -> None:
    today = journey.ui("today")
    journey.goto("/today")
    to_playwright(journey.page, today.heading).wait_for(state="visible")
    to_playwright(journey.page, today.upcoming).wait_for(state="visible")


def test_today_promote_opens_overlay(journey: Journey) -> None:
    if journey.target != "mockup":
        pytest.skip("the app promote dialog is ported in T-UR07b; click-through is a handoff flow")
    today = journey.ui("today")
    journey.goto("/today")
    page: Any = journey.page
    to_playwright(page, today.promote).first.click()
    page.wait_for_url("**/pages/overlays/promote--*.html")
    to_playwright(page, PROMOTE_DIALOG_HEADING).first.wait_for(state="visible")
