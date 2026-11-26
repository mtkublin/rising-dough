"""E2E: the picked recent category chip leads the row (F9, ADR-0151 amendment 2026-11-25).

The handoff's new-entry dialog shows the chosen chip first, checked; the app renders the chip row
on the server, so ``combobox.js`` moves the checked chip to the front when one is picked.
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from budget_planner.clock import utc_now
from tests.e2e.forms import add_happened, wait_for_htmx
from tests.e2e.ui_actions import open_new_entry
from tests.ui_map import entries, rd_fragments as f
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e

_YESTERDAY = (utc_now().date() - timedelta(days=1)).isoformat()  # inside the 90-day recent window
_CHIP_NAMES = "els => els.map(e => e.parentElement.textContent.trim())"


def test_picked_chip_moves_to_the_front_and_nothing_is_dropped(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, _ = live_server
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "100.00"},
    ).ok
    for name in ("Groceries", "Transport", "Takeaway"):
        assert page.request.post(
            f"{base_url}/categories", form={"name": name, "direction": "expense"}
        ).ok
    page.goto(f"{base_url}/ledger?view=actual")
    for category in ("Groceries", "Transport", "Takeaway"):
        add_happened(
            page,
            category=category,
            account="Checking",
            amount="1.00",
            day=_YESTERDAY,
            note=category,
        )
    page.goto(f"{base_url}/ledger?view=actual")
    wait_for_htmx(page)
    open_new_entry(page)
    radios = to_playwright(page, f.category_recent_radios.inside(entries.category_group))
    before = radios.evaluate_all(_CHIP_NAMES)
    assert sorted(before) == ["Groceries", "Takeaway", "Transport"]
    last = before[-1]

    radios.last.click(
        force=True
    )  # one click, no stability wait: the dialog is refreshed by the pick

    after = radios.evaluate_all(_CHIP_NAMES)
    assert after[0] == last
    assert sorted(after) == sorted(before)
    expect(radios.first).to_be_checked()


def test_arrow_keys_walk_the_group_without_reordering(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, _ = live_server
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "100.00"},
    ).ok
    for name in ("Groceries", "Transport", "Takeaway"):
        assert page.request.post(
            f"{base_url}/categories", form={"name": name, "direction": "expense"}
        ).ok
    page.goto(f"{base_url}/ledger?view=actual")
    for category in ("Groceries", "Transport", "Takeaway"):
        add_happened(
            page,
            category=category,
            account="Checking",
            amount="1.00",
            day=_YESTERDAY,
            note=category,
        )
    page.goto(f"{base_url}/ledger?view=actual")
    wait_for_htmx(page)
    open_new_entry(page)
    radios = to_playwright(page, f.category_recent_radios.inside(entries.category_group))
    before = radios.evaluate_all(_CHIP_NAMES)
    radios.first.focus()

    page.keyboard.press("ArrowRight")
    expect(radios.nth(1)).to_be_checked()
    expect(radios.nth(1)).to_be_focused()
    page.keyboard.press("ArrowRight")
    expect(radios.nth(2)).to_be_checked()
    expect(radios.nth(2)).to_be_focused()
    page.keyboard.press("ArrowLeft")
    expect(radios.nth(1)).to_be_checked()

    assert radios.evaluate_all(_CHIP_NAMES) == before  # the keyboard never reorders the row


def test_mouse_click_on_a_listed_category_selects_it(
    live_server: tuple[str, Path], page: Page
) -> None:
    """A human press (down, a pause, up) on a row of the full list picks it (T-UR54).

    The press moves focus off the search field; the panel must not close before the click lands.
    """
    base_url, _ = live_server
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "100.00"},
    ).ok
    for name in ("Groceries", "Transport"):
        assert page.request.post(
            f"{base_url}/categories", form={"name": name, "direction": "expense"}
        ).ok
    page.goto(f"{base_url}/ledger?view=actual")
    wait_for_htmx(page)
    open_new_entry(page)
    to_playwright(page, entries.category_search).click()
    option = to_playwright(page, f.category_option("Transport").inside(entries.dialog))
    box = option.bounding_box()
    assert box is not None
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.wait_for_timeout(250)
    page.mouse.up()

    picked = page.locator('[data-js="combobox"] input[type="hidden"][name="category"]')
    expect(picked).to_have_count(1)
    assert picked.input_value() != ""
    expect(to_playwright(page, entries.category_search)).to_contain_text("Transport")
    expect(page.locator(".rd-catpick")).to_be_hidden()
