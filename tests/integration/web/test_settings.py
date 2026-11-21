"""T-067 — Settings drawer router.

The drawer is a right-side slide-over fragment loaded via HTMX into
``#drawer-root``. These tests cover:

- Default tab is Categories when no ``?tab=`` is supplied.
- Each tab renders its own panel content.
- The drawer root HTML carries the ARIA shape the overlay-stack expects.
- ``/settings/close`` returns an empty body so HTMX can clear the drawer.
- Categories CRUD endpoints keep working (verifies the drawer re-uses the
  existing router rather than duplicating business logic).
"""

from __future__ import annotations

from bs4 import BeautifulSoup, Tag
from fastapi.testclient import TestClient


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
    assert ("FX cache" in response.text) or ("No FX rates cached yet." in response.text)


def test_settings_prefs_tab(client: TestClient) -> None:
    response = client.get("/settings?tab=prefs")
    assert response.status_code == 200
    soup = _soup(response.text)
    panel = soup.find(id="panel-prefs")
    assert panel is not None and isinstance(panel, Tag)
    base = soup.select_one('[data-pref="base-currency"]')
    tz = soup.select_one('[data-pref="display-timezone"]')
    assert base is not None and isinstance(base, Tag)
    assert tz is not None and isinstance(tz, Tag)
    assert "PLN" in base.get_text()
    assert "Europe/Warsaw" in tz.get_text()


def test_drawer_is_dialog(client: TestClient) -> None:
    """Rising Dough v2: Settings is a full page (ADR-0051 §7).

    The drawer is still rendered when an HTMX request asks for it (header
    HX-Request: true), so this test now asserts the HX variant.
    """
    response = client.get("/settings", headers={"HX-Request": "true"})
    soup = _soup(response.text)
    drawer = soup.find("aside", attrs={"role": "dialog"})
    assert drawer is not None and isinstance(drawer, Tag)
    assert drawer.get("aria-modal") == "true"
    assert drawer.get("aria-labelledby") == "drawer-title"
    title = soup.find(id="drawer-title")
    assert title is not None and isinstance(title, Tag)


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
    """Categories CRUD endpoints (which the drawer re-uses) stay functional."""
    create = client.post("/categories", data={"name": "Test", "direction": "expense"})
    assert create.status_code == 200
    assert "Test" in create.text
    assert "budget-stale" in create.headers.get("HX-Trigger", "")

    # The drawer rendering should include the freshly-created row.
    drawer = client.get("/settings?tab=categories")
    assert drawer.status_code == 200
    assert "Test" in drawer.text


def test_settings_nav_link_opens_drawer_via_htmx(client: TestClient) -> None:
    """Rising Dough v2 — Settings is a page link (no drawer) per ADR-0051 §1."""
    response = client.get("/today")
    soup = _soup(response.text)
    footer = soup.select_one(".rd-rail__footer .rd-nav__link")
    assert footer is not None
    assert footer.get("href") == "/settings"
