"""Planned empty state: new entry opens the dialog in place and saves into the page (T-UR83)."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.e2e.ui_actions import choose_category, fill_stable, quiesce, save_entry
from tests.ui_map import entries, ledger
from tests.ui_map.locator import role, to_playwright

pytestmark = pytest.mark.e2e


def test_empty_planned_new_entry_saves_into_the_page(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, db_path = live_server
    forms: list[tuple[str, dict[str, str | float | bool]]] = [
        ("/accounts", {"name": "Checking", "currency": "PLN", "opening_balance": "500.00"}),
        ("/categories", {"name": "Rent", "direction": "expense"}),
    ]
    for path, form in forms:
        assert page.request.post(f"{base_url}{path}", form=form).ok
    page.goto(f"{base_url}/ledger?view=planned")
    empty = role("link", "[ new entry ]", exact=True).inside(ledger.view_table("planned"))
    to_playwright(page, empty).click()
    expect(to_playwright(page, entries.dialog)).to_be_visible()
    to_playwright(page, entries.tab_planned).click()
    expect(to_playwright(page, entries.field_due)).to_be_visible()
    choose_category(page, "Rent")
    fill_stable(to_playwright(page, entries.field_due), "2026-12-20")
    quiesce(page)
    fill_stable(to_playwright(page, entries.hero_amount), "75.00")
    save_entry(page, "planned")
    assert db_probe.scalar(db_path, "SELECT amount FROM planned_transactions") == 7500
    rows = to_playwright(page, ledger.view_table("planned"))
    expect(rows).to_be_visible()
    expect(rows).to_contain_text("75.00")
