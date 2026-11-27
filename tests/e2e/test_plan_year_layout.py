"""E2E: the Plan/year grid scrolls inside its own region, never the page (T-UR71).

The 12-month grid is wider than a phone or tablet; it scrolls sideways in its region (T-UR64 will
redesign it mobile-first). The page itself must not scroll sideways.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

_URL = "/plan?tab=year&year=2026&month=6"
_PAGE_JS = "() => [document.scrollingElement.scrollWidth, window.innerWidth]"
_REGION_JS = (
    "(region) => [region.scrollWidth, region.clientWidth, region.getBoundingClientRect().right]"
)
_OUTSIDE_JS = """() => [...document.querySelectorAll('body *')]
  .filter((el) => el.getBoundingClientRect().right > window.innerWidth + 1
    && !el.closest('.rd-table-scroll'))
  .map((el) => el.tagName.toLowerCase() + '.' + el.className)"""


@pytest.mark.parametrize("width", [1024, 375], ids=["1024", "375"])
def test_year_grid_scrolls_in_its_region_not_the_page(
    live_server: tuple[str, Path], page: Page, width: int
) -> None:
    base_url, _ = live_server
    page.set_viewport_size({"width": width, "height": 800})
    page.goto(f"{base_url}{_URL}")
    region = page.get_by_role("region", name="Budget per category and month, 2026", exact=False)
    expect(region).to_be_visible()

    scroll_width, inner_width = page.evaluate(_PAGE_JS)
    assert scroll_width <= inner_width
    region_scroll, region_client, right = region.evaluate(_REGION_JS)
    assert region_scroll > region_client
    assert right <= inner_width
    # Only the grid inside its scroll region may reach past the viewport; no ancestor does.
    assert page.evaluate(_OUTSIDE_JS) == []
