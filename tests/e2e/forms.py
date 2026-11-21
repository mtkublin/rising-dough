"""Shared helpers for e2e tests that drive the real slide-over forms (T-Q248)."""

from __future__ import annotations

from playwright.sync_api import Page, expect

PANEL = ".slide-over-root"


def pick(page: Page, name: str, label: str) -> None:
    """Choose ``label`` in the combobox backing the hidden input ``name``."""
    combo = page.locator(f"{PANEL} [data-combobox]", has=page.locator(f"input[name='{name}']"))
    combo.locator("[data-combobox-input]").click()
    combo.locator("[role='option']", has_text=label).first.click()


def wait_for_htmx(page: Page) -> None:
    """Block until htmx has loaded, so a click is not swallowed before it binds."""
    page.wait_for_function("typeof window.htmx === 'object'")


def add_happened(
    page: Page, *, category: str, account: str, amount: str, day: str, note: str
) -> None:
    """Open the Happened overlay on the current page and submit it."""
    wait_for_htmx(page)
    page.locator("[data-rd-add]:visible").first.click()
    panel = page.locator(PANEL)
    expect(panel).to_be_visible()
    pick(page, "category_id", category)
    pick(page, "account_id", account)
    panel.locator("input[name='amount']").fill(amount)
    panel.locator("input[name='operation_date']").fill(day)
    panel.locator("input[name='description']").fill(note)
    with page.expect_response(
        lambda r: r.url.endswith("/transactions") and r.request.method == "POST"
    ) as resp:
        panel.get_by_role("button", name="Add entry").click()
    assert resp.value.ok, resp.value.text()
