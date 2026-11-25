"""New-entry hero refresh vs typing (T-UR04g): an amount typed during GET /add?hero=1 survives."""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.e2e.ui_actions import choose_category, open_new_entry
from tests.ui_map import entries
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e

_HERO_URL = "**/add?*hero=1*"


def _seed(base_url: str, page: Page) -> None:
    forms: list[tuple[str, dict[str, str | float | bool]]] = [
        ("/accounts", {"name": "Checking", "currency": "PLN", "opening_balance": "500.00"}),
        ("/accounts", {"name": "Yen", "currency": "JPY", "opening_balance": "1000"}),
        ("/categories", {"name": "Groceries", "direction": "expense"}),
        ("/categories", {"name": "Salary", "direction": "income"}),
    ]
    for path, form in forms:
        assert page.request.post(f"{base_url}{path}", form=form).ok


def test_amount_typed_during_the_hero_refresh_is_kept_and_stored(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, db_path = live_server
    _seed(base_url, page)
    page.goto(f"{base_url}/today")
    open_new_entry(page)
    choose_category(page, "Groceries")
    held: list[Any] = []

    def hold(route: Any) -> None:
        held.append(route)

    # Hold the refresh so the amount is typed while it is in flight.
    page.route(_HERO_URL, hold)
    to_playwright(page, entries.field_account).select_option(label="Yen")
    for _ in range(40):
        if held:
            break
        page.wait_for_timeout(50)
    assert held, "the account change must request a hero refresh"
    amount = to_playwright(page, entries.hero_amount)
    amount.fill("1234")
    held[0].continue_()
    expect(to_playwright(page, entries.dialog)).to_contain_text("JPY")
    expect(amount).to_have_value("1234")
    expect(amount).to_have_attribute("placeholder", "0")
    to_playwright(page, entries.field_note).fill("race-added")
    to_playwright(page, entries.save).click()
    expect(to_playwright(page, entries.dialog)).not_to_be_visible()
    assert db_probe.txn_amounts(db_path, "race-added") == [1234]


def test_failed_hero_refresh_marks_the_unit_stale(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, _ = live_server
    _seed(base_url, page)
    page.goto(f"{base_url}/today")
    open_new_entry(page)
    choose_category(page, "Groceries")
    page.route(_HERO_URL, lambda route: route.fulfill(status=500, body="boom"))
    to_playwright(page, entries.field_account).select_option(label="Yen")
    expect(to_playwright(page, entries.dialog)).to_contain_text("\N{EM DASH}")


def _hold_hero(page: Page) -> list[Any]:
    held: list[Any] = []

    def hold(route: Any) -> None:
        held.append(route)

    page.route(_HERO_URL, hold)
    return held


def _wait_for(page: Page, held: list[Any], count: int) -> None:
    for _ in range(60):
        if len(held) >= count:
            return
        page.wait_for_timeout(50)
    raise AssertionError(f"expected {count} hero request(s), saw {len(held)}")


def test_newer_hero_refresh_supersedes_the_older_one(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, _ = live_server
    _seed(base_url, page)
    page.goto(f"{base_url}/today")
    open_new_entry(page)
    choose_category(page, "Groceries")
    held = _hold_hero(page)
    to_playwright(page, entries.field_account).select_option(label="Yen")
    _wait_for(page, held, 1)
    # A second change while the first refresh is in flight: category Salary (income, sign +).
    to_playwright(page, entries.category_search).click()
    query = to_playwright(page, entries.category_query)
    query.fill("Salary")
    query.press("Enter")
    _wait_for(page, held, 2)
    for route in reversed(held):  # the older response arrives last: it must not win
        with contextlib.suppress(Exception):  # the superseded request was aborted by htmx
            route.continue_()
    dialog = to_playwright(page, entries.dialog)
    expect(dialog).to_contain_text("JPY")
    expect(dialog).to_contain_text("+")
    expect(dialog).not_to_contain_text("\N{MINUS SIGN}")


def test_save_wins_over_a_hero_refresh_in_flight(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    _seed(base_url, page)
    page.goto(f"{base_url}/today")
    open_new_entry(page)
    choose_category(page, "Groceries")
    held = _hold_hero(page)
    to_playwright(page, entries.field_account).select_option(label="Checking")
    to_playwright(page, entries.field_account).select_option(label="Yen")
    _wait_for(page, held, 1)
    to_playwright(page, entries.hero_amount).fill("777")
    to_playwright(page, entries.field_note).fill("save-wins")
    to_playwright(page, entries.save).click()
    expect(to_playwright(page, entries.dialog)).not_to_be_visible()
    assert db_probe.txn_amounts(db_path, "save-wins") == [777]
