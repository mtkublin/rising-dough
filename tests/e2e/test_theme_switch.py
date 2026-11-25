"""Theme switch on Settings > Preferences (T-UR27; ADR-0134 section 8, ADR-0113).

Client-only: ``localStorage["rd-theme"]`` plus ``<html data-theme>``. The ``page``
behind ``journey`` fails the test on any CSP violation under the prod policy.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e.mockup_target import Journey
from tests.ui_map import settings
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e

_ROUTE = "/settings?tab=prefs"
_THEME_JS = "document.documentElement.dataset.theme ?? null"
_BG_JS = "getComputedStyle(document.body).backgroundColor"


def _opt(journey: Journey, value: str) -> Any:
    return to_playwright(journey.page, settings.theme_option(value))


def _pressed(journey: Journey) -> list[str]:
    return [
        v
        for v in ("system", "light", "dark")
        if _opt(journey, v).get_attribute("aria-pressed") == "true"
    ]


def test_default_is_system_without_attribute(journey: Journey) -> None:
    journey.goto(_ROUTE)
    assert journey.page.evaluate(_THEME_JS) is None
    assert _pressed(journey) == ["system"]


def test_dark_sets_attribute_and_survives_reload(journey: Journey) -> None:
    journey.goto(_ROUTE)
    _opt(journey, "dark").click()
    assert journey.page.evaluate(_THEME_JS) == "dark"
    assert journey.page.evaluate("localStorage.getItem('rd-theme')") == "dark"
    journey.page.reload()
    assert journey.page.evaluate(_THEME_JS) == "dark"
    assert _pressed(journey) == ["dark"]
    # other pages pick it up before first paint
    journey.goto("/today")
    assert journey.page.evaluate(_THEME_JS) == "dark"


def test_system_follows_prefers_color_scheme(journey: Journey) -> None:
    page: Any = journey.page
    page.emulate_media(color_scheme="dark")
    journey.goto(_ROUTE)
    _opt(journey, "light").click()
    light_bg = page.evaluate(_BG_JS)
    _opt(journey, "system").click()
    assert page.evaluate(_THEME_JS) is None
    assert page.evaluate("localStorage.getItem('rd-theme')") == "system"
    dark_bg = page.evaluate(_BG_JS)
    assert dark_bg != light_bg
    page.emulate_media(color_scheme="light")
    assert page.evaluate(_BG_JS) == light_bg
