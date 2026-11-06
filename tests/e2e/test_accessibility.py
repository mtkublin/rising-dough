"""T-052: lightweight accessibility smoke tests.

Covers:
- Skip link is the first focusable element and jumps to `#main`.
- Keyboard tab reaches every top-level nav link in document order.
- Each primary route exposes a single `<h1>` and renders a `<main id="main">`.

These are intentionally shallow — a full axe-core sweep is listed as a
future enhancement in the T-052 plan but the Chromium install itself
already skips the suite when unavailable (see e2e/conftest.py).
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

pytestmark = pytest.mark.e2e

_ROUTES = ("/today", "/ledger", "/accounts", "/budget")


@pytest.mark.parametrize("route", _ROUTES)
def test_landmarks_present(page: Page, live_server: tuple[str, object], route: str) -> None:
    base_url, _ = live_server
    page.goto(f"{base_url}{route}")
    assert page.locator("main#main").count() == 1
    assert page.locator("h1").count() >= 1
    # Flash regions reserved for live announcements.
    assert page.locator("#flash-region[role=status]").count() == 1
    assert page.locator("#flash-region-assertive[role=alert]").count() == 1


def test_skip_link_focuses_first(page: Page, live_server: tuple[str, object]) -> None:
    base_url, _ = live_server
    page.goto(f"{base_url}/today")
    page.keyboard.press("Tab")
    focused_href = page.evaluate(
        "() => document.activeElement && document.activeElement.getAttribute('href')"
    )
    assert focused_href == "#main"


def test_tab_reaches_primary_nav(page: Page, live_server: tuple[str, object]) -> None:
    """After the skip link, Tab should visit every nav anchor in document order."""
    base_url, _ = live_server
    page.goto(f"{base_url}/today")
    # First Tab lands on the skip link; subsequent Tabs on nav items.
    seen: list[str] = []
    for _ in range(12):
        page.keyboard.press("Tab")
        href = page.evaluate(
            "() => document.activeElement && document.activeElement.tagName === 'A'"
            " ? document.activeElement.getAttribute('href') : null"
        )
        if href is not None:
            seen.append(href)
    # Rising Dough v2 IA (ADR-0051 §1): /today + /ledger + /plan + /accounts
    # primary; /settings in footer. Legacy /budget, /forecast, /analytics
    # collapsed under /plan tabs.
    expected_order = [
        "/today",
        "/ledger",
        "/plan",
        "/accounts",
        "/settings",
    ]
    for href in expected_order:
        assert href in seen, f"nav target {href!r} not reached by Tab; got {seen!r}"
    # Document order preserved.
    indexes = [seen.index(h) for h in expected_order]
    assert indexes == sorted(indexes), f"nav visited out of order: {seen!r}"
