"""Recurring empty state and the day of month default (T-UR78, T-UR79; R18, R19)."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.e2e.ui_actions import (
    choose_category,
    fill_stable,
    quiesce,
    save_entry,
)
from tests.ui_map import entries, ledger
from tests.ui_map.locator import role, to_playwright

pytestmark = pytest.mark.e2e


def _seed(base_url: str, page: Page) -> None:
    forms: list[tuple[str, dict[str, str | float | bool]]] = [
        ("/accounts", {"name": "Checking", "currency": "PLN", "opening_balance": "500.00"}),
        ("/categories", {"name": "Rent", "direction": "expense"}),
    ]
    for path, form in forms:
        assert page.request.post(f"{base_url}{path}", form=form).ok


def _open_repeats(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/ledger?view=recurring")
    empty = role("link", "[ new entry ]", exact=True).inside(ledger.view_table("recurring"))
    to_playwright(page, empty).click()
    expect(to_playwright(page, entries.dialog)).to_be_visible()
    to_playwright(page, entries.tab_repeats).click()
    expect(to_playwright(page, entries.field_day)).to_be_visible()


def test_empty_recurring_new_entry_saves_into_the_page(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, db_path = live_server
    _seed(base_url, page)
    _open_repeats(page, base_url)
    choose_category(page, "Rent")
    fill_stable(to_playwright(page, entries.field_start), "2026-12-06")
    quiesce(page)
    fill_stable(to_playwright(page, entries.hero_amount), "50.00")
    save_entry(page, "repeats")
    assert db_probe.scalar(db_path, "SELECT day_of_month FROM recurring_rules") == 6
    rows = to_playwright(page, ledger.view_table("recurring"))
    expect(rows).to_be_visible()
    expect(rows).to_contain_text("50.00")


def test_day_of_month_follows_the_start_date_until_typed(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, _db_path = live_server
    _seed(base_url, page)
    _open_repeats(page, base_url)
    start = to_playwright(page, entries.field_start)
    day = to_playwright(page, entries.field_day)
    fill_stable(start, "2026-12-06")
    expect(day).to_have_value("6")
    fill_stable(day, "15")
    fill_stable(start, "2026-12-09")
    expect(day).to_have_value("15")
