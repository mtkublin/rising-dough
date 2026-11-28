"""T-067, T-UR13 -- Settings pages on the new shell (categories, currency and FX, preferences).

Markup is inspected through the UI map (ADR-0106 section 2); route contracts live in
``tests/contract/test_settings.py``. Here: exact values the pages print, the close fragment, the
unknown-tab rule, and that the categories the page reuses keep working.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from tests.ui_map import _html, settings as ui


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


def _write_rate(db: sqlite3.Connection) -> None:
    db.execute(
        "INSERT INTO fx_rates (date, from_ccy, to_ccy, rate) "
        "VALUES ('2026-01-05', 'EUR', 'PLN', '4.25')"
    )
    db.commit()


def test_settings_default_tab_is_categories_with_expense_and_system_groups(
    client: TestClient, db: sqlite3.Connection
) -> None:
    response = client.get("/settings")
    assert response.status_code == 200
    assert _html.text_of(response.text, ui.heading) == "Categories"
    assert _html.exists(response.text, ui.category_slot)
    groups = _html.texts(response.text, ui.section_headings)
    assert any(g.startswith("System") for g in groups)
    # The seeded system categories are listed as locked rows, no edit or archive link.
    system = db.execute("SELECT id FROM categories WHERE is_system = 1 LIMIT 1").fetchone()[0]
    assert "locked" in _html.text_of(response.text, ui.category_row(system))


def test_settings_fx_tab_empty_then_lists_the_cached_rate(
    client: TestClient, db: sqlite3.Connection
) -> None:
    empty = client.get("/settings?tab=fx")
    assert empty.status_code == 200
    assert _html.text_of(empty.text, ui.fx_heading) == "FX cache"
    assert not _html.exists(empty.text, ui.fx_table)
    assert "No FX rates cached yet" in _html.text_of(empty.text, ui.panel)

    _write_rate(db)
    full = client.get("/settings?tab=fx")
    row = _html.text_of(full.text, ui.fx_row("EUR → PLN"))
    assert "EUR → PLN" in row
    assert "2026-01-05" in row
    assert "4.25" in row


def test_settings_prefs_tab_prints_base_currency_and_timezone(
    client: TestClient, settings: Settings
) -> None:
    response = client.get("/settings?tab=prefs")
    assert response.status_code == 200
    assert _html.texts(response.text, ui.pref_terms) == ["BASE CURRENCY", "DISPLAY TIMEZONE"]
    assert _html.texts(response.text, ui.pref_values) == [
        settings.base_currency,
        settings.display_timezone,
    ]
    assert _html.exists(response.text, ui.prefs_panel_heading)


def test_settings_close_fragment(client: TestClient) -> None:
    response = client.get("/settings/close")
    assert response.status_code == 200
    assert response.text == ""


def test_settings_invalid_tab_is_422(client: TestClient) -> None:
    """An unknown tab is a 422 (T-Q294); an empty one still defaults to Categories."""
    assert client.get("/settings?tab=bogus").status_code == 422
    response = client.get("/settings?tab=")
    assert response.status_code == 200
    assert _html.text_of(response.text, ui.heading) == "Categories"


def test_created_category_is_listed_on_the_page(client: TestClient) -> None:
    """The categories router the page reuses: a created row appears in the list."""
    create = client.post("/categories", data={"name": "Test", "direction": "expense"})
    assert create.status_code == 200
    assert "Test" in _html.text_of(create.text, ui.any_category_row)
    assert "budget-stale" in create.headers.get("HX-Trigger", "")

    page = client.get("/settings?tab=categories")
    assert page.status_code == 200
    assert "Test" in _html.text_of(page.text, ui.category_slot)


def test_archived_category_is_not_listed(client: TestClient, db: sqlite3.Connection) -> None:
    """ADR-0136: an archived category leaves the settings list (it is restorable elsewhere)."""
    client.post("/categories", data={"name": "Hobby", "direction": "expense"})
    cat = db.execute("SELECT id FROM categories WHERE name = 'Hobby'").fetchone()[0]
    assert "Hobby" in _html.text_of(client.get("/settings").text, ui.category_slot)
    assert client.post(f"/categories/{cat}/archive").status_code == 204
    assert "Hobby" not in _html.text_of(client.get("/settings").text, ui.category_slot)


def test_settings_nav_links_to_the_page_not_a_drawer(client: TestClient) -> None:
    """Rising Dough v2 -- Settings is a page link (no drawer) per ADR-0051 section 1."""
    response = client.get("/today")
    hrefs = {a.get("href") for a in _html.resolve(response.text, ui.any_link)}
    assert "/settings" in hrefs
