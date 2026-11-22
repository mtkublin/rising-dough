"""T-067 — Settings page, Rising Dough v2 full page (ADR-0051 §7).

Markup is inspected through the UI map (ADR-0106 section 2); route contracts
live in ``tests/contract/test_settings.py``. Here: the HTMX drawer variant, the
close fragment, and that the Categories CRUD the page reuses keeps working.
"""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag
from fastapi.testclient import TestClient

from tests.ui_map import _html, settings as ui


def _soup(response_text: str) -> BeautifulSoup:
    return BeautifulSoup(response_text, "html.parser")


def test_settings_default_tab_is_categories(client: TestClient) -> None:
    response = client.get("/settings")
    assert response.status_code == 200
    soup = _soup(response.text)
    panel = soup.find(id="panel-categories")
    assert panel is not None and isinstance(panel, Tag)
    assert panel.get("role") == "tabpanel"
    active_tab = soup.find(id="tab-categories")
    assert active_tab is not None and isinstance(active_tab, Tag)
    assert active_tab.get("aria-selected") == "true"
    # The Categories panel exposes the familiar CRUD scaffolding.
    assert soup.find(id="cat-form-slot") is not None


def test_settings_fx_tab(client: TestClient) -> None:
    response = client.get("/settings?tab=fx")
    assert response.status_code == 200
    soup = _soup(response.text)
    panel = soup.find(id="panel-fx")
    assert panel is not None and isinstance(panel, Tag)
    tab = soup.find(id="tab-fx")
    assert tab is not None and isinstance(tab, Tag)
    assert tab.get("aria-selected") == "true"
    # Either the empty-state hint or the FX table should render.
    assert _html.exists(response.text, ui.fx_heading) or (
        "No FX rates cached yet." in _html.page_text(response.text)
    )


def test_settings_prefs_tab(client: TestClient) -> None:
    response = client.get("/settings?tab=prefs")
    assert response.status_code == 200
    soup = _soup(response.text)
    panel = soup.find(id="panel-prefs")
    assert panel is not None and isinstance(panel, Tag)
    terms = _html.texts(response.text, ui.pref_terms)
    values = _html.texts(response.text, ui.pref_values)
    assert terms == ["Base currency", "Display timezone"]
    assert "PLN" in values[0]
    assert "Europe/Warsaw" in values[1]


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


def test_settings_invalid_tab_falls_back_to_default(client: TestClient) -> None:
    """Invalid tab identifiers degrade to the Categories panel rather than 500."""
    response = client.get("/settings?tab=bogus")
    assert response.status_code == 200
    soup = _soup(response.text)
    assert soup.find(id="panel-categories") is not None


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
