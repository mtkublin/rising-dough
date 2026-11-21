"""E2E under the prod CSP: planned form validation errors (T-D153, ADR-0113)."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.e2e.ui_actions import pick
from tests.ui_map import ledger, shell, today_app
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
    assert page.request.post(
        f"{base_url}/categories", form={"name": "Groceries", "direction": "expense"}
    ).ok
    page.goto(f"{base_url}/today")
    assert page.evaluate("typeof window.htmx") == "object"
    to_playwright(page, today_app.add_planned).first.click()
    panel = to_playwright(page, shell.slideover)
    expect(panel).to_be_visible()
    pick(page, ledger.field_category, "Groceries")
    pick(page, ledger.field_account, "Checking")
    pick(page, ledger.field_dest_account, "Checking")
    to_playwright(page, ledger.field_amount.inside(shell.slideover)).fill("10.00")
    to_playwright(page, ledger.add_entry.inside(shell.slideover)).click()
    expect(to_playwright(page, ledger.form_errors.inside(shell.slideover))).to_contain_text(
        "must differ"
    )
    expect(panel).to_be_visible()
    # DB: the rejected planned entry was not stored.
    assert db_probe.scalar(db_path, "SELECT COUNT(*) FROM planned_transactions") == 0
