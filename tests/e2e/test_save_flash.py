"""A successful planned save from the new-entry dialog flashes on every page (T-UR96)."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.e2e.ui_actions import (
    choose_account,
    choose_category,
    fill_stable,
    open_new_entry,
    save_entry,
)
from tests.ui_map import entries, rd_shell
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e

PAGES = ["/today", "/ledger", "/ledger?tab=planned", "/plan", "/accounts"]


@pytest.mark.parametrize("path", PAGES)
def test_planned_save_shows_its_flash(live_server: tuple[str, Path], page: Page, path: str) -> None:
    base_url, db_path = live_server
    forms: list[tuple[str, dict[str, str | float | bool]]] = [
        ("/accounts", {"name": "Checking", "currency": "PLN", "opening_balance": "500.00"}),
        ("/categories", {"name": "Groceries", "direction": "expense"}),
    ]
    for form_path, form in forms:
        assert page.request.post(f"{base_url}{form_path}", form=form).ok
    page.goto(f"{base_url}{path}")
    open_new_entry(page)
    to_playwright(page, entries.tab_planned).click()
    choose_category(page, "Groceries")
    choose_account(page, "Checking")
    fill_stable(to_playwright(page, entries.hero_amount), "12.34")
    fill_stable(to_playwright(page, entries.field_note), "flash-check")
    save_entry(page, "planned")
    expect(to_playwright(page, rd_shell.flash_saved)).to_contain_text("Planned entry saved")
    expect(to_playwright(page, entries.dialog)).not_to_be_visible()
    stored = db_probe.scalar(
        db_path, "SELECT amount_minor FROM planned_transactions WHERE description = 'flash-check'"
    )
    assert stored == 1234
