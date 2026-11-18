"""E2E under the prod CSP: planned form validation errors (T-D153, ADR-0113)."""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.e2e

_PANEL = ".slide-over-root"


def _pick(page: Page, name: str, label: str) -> None:
    """Choose ``label`` in the combobox backing the hidden input ``name``."""
    combo = page.locator(f"{_PANEL} [data-combobox]", has=page.locator(f"input[name='{name}']"))
    combo.locator("[data-combobox-input]").click()
    combo.locator("[role='option']", has_text=label).first.click()


def test_same_source_and_dest_shows_error_in_open_panel(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, _ = live_server
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "500.00"},
    ).ok
    assert page.request.post(
        f"{base_url}/categories", form={"name": "Groceries", "direction": "expense"}
    ).ok
    page.goto(f"{base_url}/today")
    assert page.evaluate("typeof window.htmx") == "object"
    page.get_by_role("button", name="+ Planned").first.click()
    panel = page.locator(_PANEL)
    expect(panel).to_be_visible()
    _pick(page, "category_id", "Groceries")
    _pick(page, "account_id", "Checking")
    _pick(page, "dest_account_id", "Checking")
    panel.locator("input[name='amount']").fill("10.00")
    panel.locator("form button[type='submit']").first.click()
    expect(panel.get_by_role("alert")).to_contain_text("must differ")
    expect(panel).to_be_visible()
