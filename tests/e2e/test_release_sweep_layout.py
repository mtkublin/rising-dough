"""E2E: release-sweep layout fixes (SWEEPCSS, T-UR16 follow-up).

At 768 and 1024 the amount column of every wide table is inside its scroll region without
scrolling; at 320 the decorative auth loaf neither overlaps the greeting nor leaves the viewport;
at 320 and 375 the forecast chart and the new-entry recent-chip strip stay inside their containers.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from playwright.sync_api import (
    Browser,
    BrowserContext,
    FloatRect,
    Page,
    StorageState,
    ViewportSize,
)

from tests.e2e import db_probe
from tests.ui_map import entries, ledger, plan_forecast, rd_shell
from tests.ui_map.locator import Locator as UiLocator, role, to_playwright

pytestmark = pytest.mark.e2e

# Every wide table sits in a labelled scroll region; the forecast chart has its own (excluded).
TABLE_REGION = role("region", re.compile(r"^(?!Chart).*\(scrolls sideways\)$"))
AMOUNT_HEADER = re.compile(r"^(amount|balance|net|spent [/] budget|expires)$", re.IGNORECASE)
TABLE_ROUTES = ("/ledger", "/plan", "/forecast", "/accounts", "/settings/security")
CATEGORIES = ("Groceries", "Transport", "Restaurants and takeaway", "Subscriptions", "Savings")
TOLERANCE_PX = 1.0


def _viewport(width: int) -> ViewportSize:
    return {"width": width, "height": 900}


def _seed(base_url: str, db_path: Path, page: Page) -> None:
    post = page.request.post
    assert post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "1000.00"},
    ).ok
    acc = db_probe.account_id(db_path, "Checking")
    today = datetime.now(tz=UTC).date().isoformat()
    for name in CATEGORIES:
        assert post(f"{base_url}/categories", form={"name": name, "direction": "expense"}).ok
        cat = db_probe.category_id(db_path, name)
        assert post(f"{base_url}/budget/defaults/{cat}", form={"amount": "500.00"}).ok
        assert post(
            f"{base_url}/transactions",
            form={
                "operation_date": today,
                "category_id": cat,
                "account_id": acc,
                "amount": "12.34",
                "description": f"sweep {name}",
            },
        ).ok
    sub = db_probe.category_id(db_path, "Subscriptions")
    due = (datetime.now(tz=UTC).date() + timedelta(days=17)).isoformat()
    assert post(
        f"{base_url}/planned",
        form={
            "operation_date": due,
            "category_id": sub,
            "account_id": acc,
            "amount": "2239.80",
            "description": "sweep planned",
        },
    ).ok
    assert post(
        f"{base_url}/recurring",
        form={
            "cadence": "monthly",
            "start_date": today,
            "category_id": sub,
            "account_id": acc,
            "default_amount": "20.00",
            "default_description": "sweep rule",
        },
    ).ok


@pytest.fixture
def signed_in(
    live_server: tuple[str, Path], page: Page
) -> Iterator[tuple[str, Browser, StorageState]]:
    base_url, db_path = live_server
    _seed(base_url, db_path, page)
    browser = page.context.browser
    assert browser is not None
    yield base_url, browser, page.context.storage_state()


def _context(browser: Browser, width: int, state: StorageState | None) -> BrowserContext:
    if state is None:
        return browser.new_context(viewport=_viewport(width))
    return browser.new_context(viewport=_viewport(width), storage_state=state)


def _box(page: Page, target: UiLocator) -> FloatRect:
    box: FloatRect | None = to_playwright(page, target).first.bounding_box()
    assert box is not None, target
    return box


@pytest.mark.parametrize("width", [768, 1024])
@pytest.mark.parametrize("route", TABLE_ROUTES)
def test_amount_column_is_visible_without_scrolling(
    signed_in: tuple[str, Browser, StorageState], route: str, width: int
) -> None:
    base_url, browser, state = signed_in
    context = _context(browser, width, state)
    try:
        tab = context.new_page()
        tab.goto(f"{base_url}{route}")
        regions = to_playwright(tab, TABLE_REGION)
        assert regions.count() >= 1, route
        for index in range(regions.count()):
            region = regions.nth(index)
            if not region.is_visible():
                continue
            region_box = region.bounding_box()
            assert region_box is not None
            fits = region.evaluate("(el) => el.scrollWidth <= el.clientWidth + 1")
            assert fits, f"{route} at {width}: table wider than its scroll region"
            headers = region.get_by_role("columnheader", name=AMOUNT_HEADER)
            assert headers.count() >= 1, f"{route}: no amount-like column header"
            for h in range(headers.count()):
                box = headers.nth(h).bounding_box()
                assert box is not None
                assert (
                    box["x"] + box["width"] <= region_box["x"] + region_box["width"] + TOLERANCE_PX
                )
    finally:
        context.close()


def test_auth_loaf_clears_the_greeting_at_320(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _db_path = live_server
    browser = page.context.browser
    assert browser is not None
    context = _context(browser, 320, None)
    try:
        guest = context.new_page()
        guest.goto(f"{base_url}/auth/login")
        greeting = guest.get_by_text("Hello", exact=False).first.bounding_box()
        assert greeting is not None
        # The loaf is aria-hidden art with no role or label, so it is read through the DOM.
        loaf = guest.evaluate(
            """() => {
              const el = document.querySelector('[aria-hidden="true"][class*="loaf"]');
              if (!el || el.getClientRects().length === 0) return null;
              const r = el.getBoundingClientRect();
              return { x: r.x, y: r.y, width: r.width, height: r.height };
            }"""
        )
        if loaf is not None:
            box = loaf
            assert box["x"] + box["width"] <= 320 + TOLERANCE_PX
            overlap_x = (
                box["x"] < greeting["x"] + greeting["width"]
                and greeting["x"] < box["x"] + box["width"]
            )
            overlap_y = (
                box["y"] < greeting["y"] + greeting["height"]
                and greeting["y"] < box["y"] + box["height"]
            )
            assert not (overlap_x and overlap_y)
        assert guest.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    finally:
        context.close()


def test_planned_status_clears_the_promote_button_at_768(
    signed_in: tuple[str, Browser, StorageState],
) -> None:
    base_url, browser, state = signed_in
    context = _context(browser, 768, state)
    try:
        tab = context.new_page()
        tab.goto(f"{base_url}/ledger?view=planned")
        row = to_playwright(tab, ledger.any_planned_row).first
        promote = to_playwright(tab, ledger.promote).first
        promote_box = promote.bounding_box()
        assert promote_box is not None
        # The status is the fifth cell; its content (text and children) must end before the button.
        status_right: float = row.evaluate(
            """(el) => {
              const cell = el.children[4];
              const range = document.createRange();
              range.selectNodeContents(cell);
              const rights = [range.getBoundingClientRect().right];
              for (const c of cell.querySelectorAll('*')) {
                rights.push(c.getBoundingClientRect().right);
              }
              return Math.max(...rights);
            }"""
        )
        assert status_right <= promote_box["x"] + TOLERANCE_PX
    finally:
        context.close()


def test_category_chips_do_not_clip_in_the_recurring_table_at_768(
    signed_in: tuple[str, Browser, StorageState],
) -> None:
    base_url, browser, state = signed_in
    context = _context(browser, 768, state)
    try:
        tab = context.new_page()
        tab.goto(f"{base_url}/ledger?view=recurring")
        region = to_playwright(tab, TABLE_REGION).first
        clipped: list[str] = region.evaluate(
            """(el) => [...el.querySelectorAll('tbody td span, tbody td a')]
              .filter((c) => c.getClientRects().length && c.scrollWidth > c.clientWidth + 1)
              .map((c) => c.textContent.trim())"""
        )
        assert clipped == []
        names: list[str] = region.evaluate(
            "(el) => [...el.querySelectorAll('tbody tr')].map((r) => r.textContent)"
        )
        assert any("Subscriptions" in n for n in names)
    finally:
        context.close()


def test_forecast_chart_keeps_readable_labels_and_scrolls_inside_its_card(
    signed_in: tuple[str, Browser, StorageState],
) -> None:
    base_url, browser, state = signed_in
    context = _context(browser, 375, state)
    try:
        tab = context.new_page()
        tab.goto(f"{base_url}/forecast")
        container = to_playwright(tab, plan_forecast.chart_scroll)
        container_box = container.bounding_box()
        assert container_box is not None
        assert container_box["x"] + container_box["width"] <= 375 + TOLERANCE_PX
        scroll = container.evaluate(
            "(el) => ({ overflowX: getComputedStyle(el).overflowX,"
            " wide: el.scrollWidth > el.clientWidth })"
        )
        assert scroll == {"overflowX": "auto", "wide": True}
        label_height: float = to_playwright(tab, plan_forecast.chart).evaluate(
            "(el) => el.querySelector('text').getBoundingClientRect().height"
        )
        assert label_height >= 10
    finally:
        context.close()


@pytest.mark.parametrize("width", [320, 375])
def test_recent_chip_strip_stays_inside_the_dialog(
    signed_in: tuple[str, Browser, StorageState], width: int
) -> None:
    base_url, browser, state = signed_in
    context = _context(browser, width, state)
    try:
        tab = context.new_page()
        tab.goto(f"{base_url}/today")
        tab.wait_for_function("typeof window.htmx === 'object'")
        to_playwright(tab, rd_shell.tabbar_new_entry).click()
        group = to_playwright(tab, entries.category_group)
        group.wait_for(state="visible")
        group_box = group.bounding_box()
        assert group_box is not None
        # The recent-category strip is the group's first box.
        strip = group.evaluate(
            """(el) => {
              const box = el.querySelector('div');
              const r = box.getBoundingClientRect();
              return { right: r.right, overflowX: getComputedStyle(box).overflowX };
            }"""
        )
        assert strip["right"] <= group_box["x"] + group_box["width"] + TOLERANCE_PX
        assert strip["right"] <= width + TOLERANCE_PX
        assert strip["overflowX"] == "auto"
    finally:
        context.close()
