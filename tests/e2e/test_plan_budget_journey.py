"""Plan · budget tab on either target (T-UR11; ADR-0106, ADR-0107).

``--target=mockup`` runs the journeys against ``pages/plan/budget.html``;
the default target runs them against ``/plan?tab=budget`` seeded with one
budgeted category. Values that depend on the data (month labels, amounts) are
asserted on the app only; the structure is asserted on both.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from playwright.sync_api import expect

from tests.e2e import db_probe
from tests.e2e.mockup_target import Journey
from tests.ui_map import plan_budget, rd_fragments
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e

_CATEGORY = "Groceries"
_SAMPLE_ROW = "Groceries"  # present in the handoff sample and in the seeded app data


def _find(journey: Journey, locator: Any) -> Any:
    return to_playwright(journey.page, locator)


def _seed_app(journey: Journey, request: pytest.FixtureRequest) -> None:
    """One account and a budgeted category (app target only)."""
    if journey.target != "app":
        return
    _base, db_path = request.getfixturevalue("live_server")
    post = journey.page.request.post
    base = journey.base_url
    assert post(
        f"{base}/accounts",
        form={"name": "Checking", "currency": "PLN", "opening_balance": "5000.00"},
    ).ok
    assert post(f"{base}/categories", form={"name": _CATEGORY, "direction": "expense"}).ok
    category_id = db_probe.category_id(db_path, _CATEGORY)
    assert post(f"{base}/budget/defaults/{category_id}", form={"amount": "500.00"}).ok


def _open(journey: Journey, request: pytest.FixtureRequest) -> None:
    _seed_app(journey, request)
    journey.goto("/plan?tab=budget&year=2026&month=6" if journey.target == "app" else "/plan")
    _find(journey, plan_budget.heading).wait_for(state="visible")


def test_hero_label_tabs_and_period_are_visible(
    journey: Journey, request: pytest.FixtureRequest
) -> None:
    _open(journey, request)
    expect(_find(journey, plan_budget.hero)).to_be_visible()
    expect(_find(journey, plan_budget.tab("budget"))).to_have_attribute("aria-current", "page")
    for name in ("year", "forecast", "analytics"):
        expect(_find(journey, plan_budget.tab(name))).to_be_visible()
    expect(_find(journey, rd_fragments.period_nav)).to_be_visible()
    expect(_find(journey, plan_budget.period_trigger)).to_be_visible()


def test_table_has_a_bar_and_a_status_per_row_and_a_total(
    journey: Journey, request: pytest.FixtureRequest
) -> None:
    _open(journey, request)
    expect(_find(journey, plan_budget.table)).to_be_visible()
    expect(_find(journey, plan_budget.total_row)).to_be_visible()
    bar = _find(journey, plan_budget.bar(_SAMPLE_ROW))
    expect(bar).to_have_attribute("aria-label", re.compile(r"percent spent|over budget|no budget"))
    cells = _find(journey, plan_budget.row_cells(_SAMPLE_ROW))
    expect(cells.nth(2)).to_contain_text(re.compile(r"\d"))
    expect(cells.nth(3)).to_contain_text(re.compile(r"left|over|no budget"))


def test_period_picker_lists_twelve_months(
    journey: Journey, request: pytest.FixtureRequest
) -> None:
    _open(journey, request)
    _find(journey, plan_budget.period_trigger).click()
    picker = _find(journey, rd_fragments.period_picker)
    expect(picker).to_be_visible()
    months = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    for month in months:
        expect(_find(journey, rd_fragments.period_cell(month))).to_be_visible()


def test_row_menu_offers_the_budget_edit_and_escape_closes_it(
    journey: Journey, request: pytest.FixtureRequest
) -> None:
    _open(journey, request)
    _find(journey, plan_budget.row_menu_button(_SAMPLE_ROW)).click()
    expect(_find(journey, plan_budget.row_menu(_SAMPLE_ROW))).to_be_visible()
    item = plan_budget.edit_budget_item if journey.target == "app" else plan_budget.override_item
    expect(_find(journey, item(_SAMPLE_ROW))).to_be_visible()
    journey.page.keyboard.press("Escape")
    expect(_find(journey, plan_budget.row_menu(_SAMPLE_ROW))).to_be_hidden()


def test_period_arrows_step_months_without_writing(
    journey: Journey, request: pytest.FixtureRequest
) -> None:
    if journey.target != "app":
        pytest.skip("the handoff page has one fixed month; the arrows link to the same page")
    _open(journey, request)
    _base, db_path = request.getfixturevalue("live_server")
    writes = db_probe.scalar(db_path, "SELECT COUNT(*) FROM audit_log")
    trigger = _find(journey, plan_budget.period_trigger)
    expect(trigger).to_contain_text("June 2026")
    _find(journey, rd_fragments.period_prev).click()
    expect(trigger).to_contain_text("May 2026")
    _find(journey, rd_fragments.period_next).click()
    _find(journey, rd_fragments.period_next).click()
    expect(trigger).to_contain_text("July 2026")
    assert db_probe.scalar(db_path, "SELECT COUNT(*) FROM audit_log") == writes


def test_period_arrows_cross_the_year_boundary(
    journey: Journey, request: pytest.FixtureRequest
) -> None:
    if journey.target != "app":
        pytest.skip("the handoff page has one fixed month; the arrows link to the same page")
    _seed_app(journey, request)
    journey.goto("/plan?tab=budget&year=2026&month=1")
    trigger = _find(journey, plan_budget.period_trigger)
    _find(journey, rd_fragments.period_prev).click()
    expect(trigger).to_contain_text("December 2025")
    journey.goto("/plan?tab=budget&year=2026&month=12")
    _find(journey, rd_fragments.period_next).click()
    expect(trigger).to_contain_text("January 2027")
    expect(journey.page).to_have_url(re.compile(r"year=2027&month=1"))


def test_picker_year_arrow_swaps_the_grid_without_navigating(
    journey: Journey, request: pytest.FixtureRequest
) -> None:
    if journey.target != "app":
        pytest.skip("the handoff page has one fixed month; the arrows link to the same page")
    _open(journey, request)
    url_before = journey.page.url
    _find(journey, plan_budget.period_trigger).click()
    picker = _find(journey, rd_fragments.period_picker)
    expect(picker).to_contain_text("2026")
    _find(journey, rd_fragments.period_next_year).click()
    expect(picker).to_contain_text("2027")
    expect(picker).not_to_contain_text("jun = ")
    expect(picker).to_be_visible()
    # Keyboard: focus stays on the swapped next-year arrow, so Enter again goes to 2028.
    expect(_find(journey, rd_fragments.period_next_year)).to_be_focused()
    # htmx marks the swapped top-level node (the arrows' wrapper, not the arrows) htmx-added until
    # the settle delay ends and binds hx-get then; an Enter before that follows the plain href.
    expect(_find(journey, rd_fragments.period_picker_head)).not_to_have_class(
        re.compile(r"htmx-(added|settling)")
    )
    journey.page.keyboard.press("Enter")
    expect(picker).to_contain_text("2028")
    expect(_find(journey, rd_fragments.period_next_year)).to_be_focused()
    _find(journey, rd_fragments.period_prev_year).click()
    _find(journey, rd_fragments.period_prev_year).click()
    expect(picker).to_contain_text("2026")
    expect(picker).to_contain_text("jun = ")
    expect(picker).to_be_visible()
    _find(journey, rd_fragments.period_next_year).click()
    expect(picker).to_contain_text("2027")
    expect(journey.page).to_have_url(url_before)
    expect(_find(journey, plan_budget.period_trigger)).to_contain_text("June 2026")
    _find(journey, rd_fragments.period_cell("Mar")).click()
    expect(journey.page).to_have_url(re.compile(r"year=2027&month=3"))
    expect(_find(journey, plan_budget.period_trigger)).to_contain_text("March 2027")
