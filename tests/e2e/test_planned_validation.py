"""E2E under the prod CSP: planned form validation errors (T-D153, ADR-0113)."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.e2e.ui_actions import choose_account, choose_category, open_new_entry
from tests.ui_map import entries
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e


def test_same_source_and_dest_shows_error_in_open_panel(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, db_path = live_server
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "500.00"},
    ).ok
    page.goto(f"{base_url}/today")
    open_new_entry(page)
    to_playwright(page, entries.tab_planned).click()
    choose_category(page, "Transit")  # a transit shows its destination account
    choose_account(page, "Checking")
    to_playwright(page, entries.field_dest).select_option(label="Checking")
    to_playwright(page, entries.hero_amount).fill("10.00")
    to_playwright(page, entries.save).click()
    dialog = to_playwright(page, entries.dialog)
    expect(to_playwright(page, entries.field_error("dest_account_id"))).to_contain_text(
        "must differ"
    )
    expect(dialog).to_be_visible()
    # DB: the rejected planned entry was not stored.
    assert db_probe.scalar(db_path, "SELECT COUNT(*) FROM planned_transactions") == 0
