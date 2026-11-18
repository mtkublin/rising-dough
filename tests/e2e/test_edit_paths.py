"""E2E under the prod CSP: edit / override / promote paths (T-D151, ADR-0113).

These forms used to target ledger row ids, so they did nothing from Today,
left the slide-over open after a save, and let a 422 replace the ledger row.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e.conftest import strip_id_prefix

pytestmark = pytest.mark.e2e

_PANEL = ".slide-over-root"
_RULE_ROW = "tr[id^='recurring-']:not([id$='-expand'])"


def _today() -> datetime:
    return datetime.now(tz=UTC)


def _seed(base_url: str, page: Page) -> tuple[str, str]:
    assert page.request.post(
        f"{base_url}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "500.00"},
    ).ok
    assert page.request.post(
        f"{base_url}/categories", form={"name": "Groceries", "direction": "expense"}
    ).ok
    page.goto(f"{base_url}/accounts")
    account_id = strip_id_prefix(
        page.locator("tr[id^='account-']").first.get_attribute("id"), "account-"
    )
    page.goto(f"{base_url}/categories")
    row = page.locator("[id^='category-']", has_text="Groceries").first
    return account_id, strip_id_prefix(row.get_attribute("id"), "category-")


def _rule(base_url: str, page: Page, ids: tuple[str, str], cadence: str = "monthly") -> None:
    assert page.request.post(
        f"{base_url}/recurring",
        form={
            "cadence": cadence,
            "start_date": (_today() + timedelta(days=2)).date().isoformat(),
            "category_id": ids[1],
            "account_id": ids[0],
            "default_amount": "50.00",
            "default_description": "edit-rule",
        },
    ).ok


def _planned(base_url: str, page: Page, ids: tuple[str, str]) -> None:
    assert page.request.post(
        f"{base_url}/planned",
        form={
            "operation_date": (_today() + timedelta(days=2)).date().isoformat(),
            "category_id": ids[1],
            "account_id": ids[0],
            "amount": "25.00",
            "description": "edit-planned",
        },
    ).ok


def _ledger(base_url: str, view: str) -> str:
    lo = (_today() - timedelta(days=30)).date().isoformat()
    hi = (_today() + timedelta(days=400)).date().isoformat()
    return f"{base_url}/ledger?view={view}&date_from={lo}&date_to={hi}"


def _kebab_item(page: Page, row_selector: str, name: str) -> None:
    row = page.locator(row_selector).first
    row.locator(".kebab__trigger").click()
    row.get_by_role("menuitem", name=name).click()


def test_today_override_recurring_saves_and_closes(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, _ = live_server
    _rule(base_url, page, _seed(base_url, page))
    page.goto(f"{base_url}/today")
    assert page.evaluate("typeof window.htmx") == "object"
    page.locator("#upcoming-root").get_by_role("button", name="Override").first.click()
    panel = page.locator(_PANEL)
    expect(panel).to_be_visible()
    panel.locator("input[name='amount']").fill("77.00")
    panel.get_by_role("button", name="Save").click()
    expect(page.locator(_PANEL)).to_have_count(0)
    page.goto(_ledger(base_url, "recurring"))
    assert "77.00" in page.content()


def test_today_override_planned_saves_and_closes(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    _planned(base_url, page, _seed(base_url, page))
    page.goto(f"{base_url}/today")
    assert page.evaluate("typeof window.htmx") == "object"
    page.locator("#upcoming-root").get_by_role("button", name="Override").first.click()
    panel = page.locator(_PANEL)
    expect(panel).to_be_visible()
    panel.locator("input[name='amount']").fill("33.00")
    panel.get_by_role("button", name="Save").click()
    expect(page.locator(_PANEL)).to_have_count(0)
    page.goto(_ledger(base_url, "planned"))
    assert "33.00" in page.content()


def test_ledger_txn_edit_closes_and_row_updates(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    account_id, category_id = _seed(base_url, page)
    assert page.request.post(
        f"{base_url}/transactions",
        form={
            "operation_date": _today().date().isoformat(),
            "category_id": category_id,
            "account_id": account_id,
            "amount": "12.34",
            "description": "edit-txn",
        },
    ).ok
    page.goto(_ledger(base_url, "actual"))
    assert page.evaluate("typeof window.htmx") == "object"
    row_sel = "tr[id^='txn-']"
    _kebab_item(page, row_sel, "Edit")
    panel = page.locator(_PANEL)
    expect(panel).to_be_visible()
    panel.locator("input[name='amount']").fill("99.00")
    panel.get_by_role("button", name="Save").click()
    expect(page.locator(_PANEL)).to_have_count(0)
    expect(page.locator(row_sel).first).to_contain_text("99.00")


def test_ledger_planned_promote_closes(live_server: tuple[str, Path], page: Page) -> None:
    base_url, _ = live_server
    _planned(base_url, page, _seed(base_url, page))
    page.goto(_ledger(base_url, "planned"))
    assert page.evaluate("typeof window.htmx") == "object"
    page.locator("tr[id^='planned-p-']").get_by_role("button", name="Promote").first.click()
    panel = page.locator(_PANEL)
    expect(panel).to_be_visible()
    panel.get_by_role("button", name="Promote").click()
    expect(page.locator(_PANEL)).to_have_count(0)
    page.goto(_ledger(base_url, "actual"))
    expect(page.get_by_text("edit-planned").first).to_be_visible()


def test_override_invalid_month_shows_error_in_panel(
    live_server: tuple[str, Path], page: Page
) -> None:
    base_url, _ = live_server
    _rule(base_url, page, _seed(base_url, page), cadence="quarterly")
    page.goto(_ledger(base_url, "recurring"))
    assert page.evaluate("typeof window.htmx") == "object"
    _kebab_item(page, _RULE_ROW, "Override")
    panel = page.locator(_PANEL)
    expect(panel).to_be_visible()
    panel.locator("[data-period-next]").click()  # a month with no quarterly occurrence
    panel.locator("input[name='amount']").fill("77.00")
    panel.get_by_role("button", name="Save").click()
    expect(page.locator(_PANEL)).to_contain_text("no occurrence")
    expect(page.locator(_RULE_ROW).first).to_be_visible()
