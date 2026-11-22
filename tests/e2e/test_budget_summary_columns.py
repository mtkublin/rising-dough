"""E2E: monthly summary delta colouring and responsive columns (T-Q278, ADR-0049).

Replaces the class-name assertions (``delta--up``, ``col-hide-sm``) that lived in
``tests/integration/web/test_budget.py``: what matters is how the columns look.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

from tests.e2e import db_probe
from tests.ui_map import plan
from tests.ui_map.locator import role, to_playwright

pytestmark = pytest.mark.e2e

DELTA_COLUMN = 5  # Category, Planned, Actual, Avg/mo, YTD avg, Delta prev, ...
MOBILE = {"width": 375, "height": 800}
DESKTOP = {"width": 1440, "height": 900}


def _post(page: Page, base_url: str, path: str, form: dict[str, str | float | bool]) -> None:
    assert page.request.post(f"{base_url}{path}", form=form).ok


def _seed(page: Page, base_url: str, db_path: Path) -> None:
    _post(
        page,
        base_url,
        "/accounts",
        {"name": "Checking", "currency": "PLN", "opening_balance": "5000.00"},
    )
    acct = str(db_probe.account_id(db_path, "Checking"))
    # name -> (previous month, this month) spend.
    spend = {"Food": ("300", "500"), "Rent": ("400", "400"), "Fun": ("200", "100")}
    for name, (prev, this) in spend.items():
        _post(page, base_url, "/categories", {"name": name, "direction": "expense"})
        cat = str(db_probe.category_id(db_path, name))
        for day, amount in (("2026-09-15", prev), ("2026-10-15", this)):
            _post(
                page,
                base_url,
                "/transactions",
                {
                    "operation_date": day,
                    "category_id": cat,
                    "account_id": acct,
                    "amount": amount,
                    "description": f"{name} {day}",
                },
            )


def _delta_colour(page: Page, category: str) -> str:
    cell = to_playwright(page, plan.summary_cells(category)).nth(DELTA_COLUMN)
    return str(cell.evaluate("el => getComputedStyle(el).color"))


def test_delta_colour_follows_direction(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    _seed(page, base_url, db_path)
    page.set_viewport_size(DESKTOP)  # type: ignore[arg-type]
    page.goto(f"{base_url}/budget?year=2026&month=10")

    up, down = _delta_colour(page, "Food"), _delta_colour(page, "Fun")
    neutral = _delta_colour(page, "Rent")
    category_cell = to_playwright(page, plan.summary_cells("Rent")).nth(0)
    body_colour = str(category_cell.evaluate("el => getComputedStyle(el).color"))
    assert up != down
    assert neutral == body_colour  # a zero delta carries no up/down colour
    assert neutral not in {up, down}


def test_analytics_columns_hide_on_mobile(live_server: tuple[str, Path], page: Page) -> None:
    base_url, db_path = live_server
    _seed(page, base_url, db_path)
    page.goto(f"{base_url}/budget?year=2026&month=10")
    headers = {
        name: to_playwright(page, role("columnheader", name).inside(plan.summary_table))
        for name in ("Avg/mo", "YTD avg", "Δ prev")
    }

    page.set_viewport_size(DESKTOP)  # type: ignore[arg-type]
    for header in headers.values():
        expect(header).to_be_visible()

    page.set_viewport_size(MOBILE)  # type: ignore[arg-type]
    expect(headers["Avg/mo"]).to_be_visible()  # stays visible
    expect(headers["YTD avg"]).to_be_hidden()
    expect(headers["Δ prev"]).to_be_hidden()
