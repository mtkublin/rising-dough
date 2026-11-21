"""T-067 — Settings page, Rising Dough v2 full page (ADR-0051 §7).

Markup is inspected through the UI map (ADR-0106 section 2); route contracts
live in ``tests/contract/test_settings.py``. Here: the HTMX drawer variant, the
close fragment, and that the Categories CRUD the page reuses keeps working.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.ui_map import _html, settings as ui

HX = {"HX-Request": "true"}


def test_drawer_is_dialog(client: TestClient) -> None:
    """The drawer is still rendered when an HTMX request asks for it."""
    response = client.get("/settings", headers=HX)
    drawer = _html.resolve_one(response.text, ui.drawer)
    assert drawer.name == "aside"
    assert drawer.get("aria-modal") == "true"
    assert drawer.get("aria-labelledby") == "drawer-title"
    assert _html.exists(response.text, ui.drawer_title)


def test_settings_close_fragment(client: TestClient) -> None:
    response = client.get("/settings/close")
    assert response.status_code == 200
    assert response.text == ""


def test_categories_crud_from_drawer(client: TestClient) -> None:
    """Categories CRUD endpoints (which the page re-uses) stay functional."""
    create = client.post("/categories", data={"name": "Test", "direction": "expense"})
    assert create.status_code == 200
    assert "Test" in _html.text_of(create.text, ui.any_category_row)
    assert "budget-stale" in create.headers.get("HX-Trigger", "")

    page = client.get("/settings?tab=categories")
    assert page.status_code == 200
    assert "Test" in _html.text_of(page.text, ui.panel)


def test_settings_nav_links_to_the_page_not_a_drawer(client: TestClient) -> None:
    """Rising Dough v2 — Settings is a page link (no drawer) per ADR-0051 §1."""
    response = client.get("/today")
    hrefs = {a.get("href") for a in _html.resolve(response.text, ui.any_link)}
    assert "/settings" in hrefs
