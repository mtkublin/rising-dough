"""New app shell journeys on either target (T-UR02; ADR-0106, ADR-0107).

``--target=mockup`` runs them against the handoff (``pages/today.html`` and
``pages/settings/preferences.html``); the default target runs them against the
dev placeholder page ``/dev/shell`` that extends ``layouts/base.html``.
"""

from __future__ import annotations

import re
from typing import Any

import pytest

from tests.e2e.mockup_target import Journey
from tests.ui_map import rd_shell as shell
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e

# nav label -> (route the app link points at, handoff page suffix)
_NAV = {
    "today": ("/today", "pages/today.html"),
    "ledger": ("/ledger", "pages/ledger/actual.html"),
    "plan": ("/plan", "pages/plan/budget.html"),
    "accounts": ("/accounts", "pages/accounts.html"),
}


def _url_matches(journey: Journey, label: str) -> re.Pattern[str]:
    route, page = _NAV[label]
    tail = page if journey.target == "mockup" else route
    return re.compile(re.escape(tail) + r"$")


def _today_keys(journey: Journey) -> str:
    """The handoff board uses ``g o`` for Today; the app uses ``g t`` (ADR-0147 section 5)."""
    return "g o" if journey.target == "mockup" else "g t"


def _loc(journey: Journey, locator: Any) -> Any:
    return to_playwright(journey.page, locator)


def test_regions_and_dialog_roots_are_on_the_page(journey: Journey) -> None:
    journey.goto("/dev/shell")
    for root in (shell.modal_root, shell.drawer_root, shell.toast_root, shell.flash_region):
        assert _loc(journey, root).count() == 1
    assert _loc(journey, shell.main).count() == 1
    assert _loc(journey, shell.palette).count() == 1
    assert _loc(journey, shell.shortcuts).count() == 1
    assert _loc(journey, shell.palette_dialog).is_visible() is False
    assert _loc(journey, shell.shortcuts_dialog).is_visible() is False


def test_skip_link_is_first_tab_stop_and_targets_main(journey: Journey) -> None:
    journey.goto("/dev/shell")
    journey.page.keyboard.press("Tab")
    link = _loc(journey, shell.skip_link)
    assert link.evaluate("el => el === document.activeElement") is True
    assert link.get_attribute("href") == "#main"
    assert _loc(journey, shell.main).get_attribute("id") == "main"


def test_desktop_rail_shows_four_links_and_hides_tab_bar(journey: Journey) -> None:
    journey.page.set_viewport_size({"width": 1280, "height": 800})
    journey.goto("/dev/shell")
    assert _loc(journey, shell.header).is_visible()
    assert _loc(journey, shell.nav_desktop).is_visible()
    assert _loc(journey, shell.nav_phone).is_visible() is False
    for label in _NAV:
        assert _loc(journey, shell.nav_link(label)).is_visible(), label
    assert _loc(journey, shell.nav_link("today")).get_attribute("aria-current") == "page"
    assert _loc(journey, shell.nav_link("ledger")).get_attribute("aria-keyshortcuts") == "g l"
    assert _loc(journey, shell.nav_link("today")).get_attribute("aria-keyshortcuts") == _today_keys(
        journey
    )


def test_phone_shows_tab_bar_and_hides_desktop_rail(journey: Journey) -> None:
    journey.page.set_viewport_size({"width": 375, "height": 800})
    journey.goto("/dev/shell")
    assert _loc(journey, shell.nav_phone).is_visible()
    assert _loc(journey, shell.nav_desktop).is_visible() is False
    for label in _NAV:
        assert _loc(journey, shell.tab_link(label)).is_visible(), label


@pytest.mark.parametrize("label", ["ledger", "plan", "accounts"])
def test_rail_link_navigates(journey: Journey, label: str) -> None:
    journey.goto("/dev/shell")
    _loc(journey, shell.nav_link(label)).click()
    journey.page.wait_for_url(_url_matches(journey, label))


def test_go_to_shortcut_navigates(journey: Journey) -> None:
    journey.goto("/dev/shell")
    journey.page.keyboard.press("g")
    journey.page.keyboard.press("l")
    journey.page.wait_for_url(_url_matches(journey, "ledger"))


def test_palette_opens_filters_and_goes(journey: Journey) -> None:
    journey.goto("/dev/shell")
    journey.page.keyboard.press("Control+k")
    assert _loc(journey, shell.palette_dialog).is_visible()
    assert _loc(journey, shell.palette_input).evaluate("el => el === document.activeElement")
    assert _loc(journey, shell.palette_options).count() == 7
    _loc(journey, shell.palette_input).fill("ledg")
    assert _loc(journey, shell.palette_options).count() == 1
    assert _loc(journey, shell.palette_option("Go to Ledger")).is_visible()
    journey.page.keyboard.press("Enter")
    journey.page.wait_for_url(_url_matches(journey, "ledger"))


def test_palette_lists_today_with_its_keys(journey: Journey) -> None:
    journey.goto("/dev/shell")
    journey.page.keyboard.press("Control+k")
    today = _loc(journey, shell.palette_option("Go to Today"))
    assert today.inner_text().split() == ["Go", "to", "Today", *_today_keys(journey).split()]


def test_palette_escape_closes(journey: Journey) -> None:
    journey.goto("/dev/shell")
    journey.page.keyboard.press("Control+k")
    journey.page.keyboard.press("Escape")
    assert _loc(journey, shell.palette_dialog).is_visible() is False


def test_question_mark_opens_shortcuts_and_escape_closes(journey: Journey) -> None:
    journey.goto("/dev/shell")
    journey.page.keyboard.press("?")
    assert _loc(journey, shell.shortcuts_dialog).is_visible()
    journey.page.keyboard.press("Escape")
    assert _loc(journey, shell.shortcuts_dialog).is_visible() is False


def test_shortcuts_button_and_close_button(journey: Journey) -> None:
    journey.goto("/dev/shell")
    _loc(journey, shell.shortcuts_button).click()
    assert _loc(journey, shell.shortcuts_dialog).is_visible()
    _loc(journey, shell.shortcuts_close).click()
    assert _loc(journey, shell.shortcuts_dialog).is_visible() is False


def test_theme_switch_sets_and_persists_theme(journey: Journey) -> None:
    journey.goto("/dev/shell?view=theme")
    page: Any = journey.page
    _loc(journey, shell.theme_option("dark")).click()
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    assert _loc(journey, shell.theme_option("dark")).get_attribute("aria-pressed") == "true"
    page.reload()
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    assert _loc(journey, shell.theme_option("dark")).get_attribute("aria-pressed") == "true"
    _loc(journey, shell.theme_option("light")).click()
    assert page.evaluate("document.documentElement.dataset.theme") == "light"
    assert page.evaluate("window.localStorage.getItem('rd-theme')") == "light"
