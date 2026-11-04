"""T-D50 / ADR-0076: `/` redirects to Today; shell + navigation on /today."""

from __future__ import annotations

from bs4 import BeautifulSoup
from fastapi.testclient import TestClient


def test_root_redirects_to_today(client: TestClient) -> None:
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/today"


def test_root_head_redirects_to_today(client: TestClient) -> None:
    r = client.head("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/today"


def test_root_follows_to_today_page(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert str(r.url).endswith("/today")


def test_legacy_overview_fragment_is_gone(client: TestClient) -> None:
    assert client.get("/overview/upcoming").status_code == 404


def test_brand_link_points_to_today(client: TestClient) -> None:
    soup = BeautifulSoup(client.get("/today").text, "html.parser")
    brand = soup.select_one("a.rd-wordmark")
    assert brand is not None
    assert brand["href"] == "/today"


def test_nav_links_present(client: TestClient) -> None:
    """Rising Dough v2 rail — ADR-0051 §1 IA.

    Nav collapses v1 Budget + Forecast + Analytics into /plan (tabs).
    Legacy /transactions, /planned, /recurring still 302 but the rail no
    longer links to them directly.
    """
    r = client.get("/today")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    hrefs = {a["href"] for a in soup.select("nav a")}
    for path in ("/today", "/ledger", "/plan", "/accounts", "/settings"):
        assert path in hrefs, f"nav missing {path}"
    assert "/transactions" not in hrefs
    assert "/budget" not in hrefs
    assert "/forecast" not in hrefs


def test_nav_has_four_primary_items_plus_settings(client: TestClient) -> None:
    r = client.get("/today")
    soup = BeautifulSoup(r.text, "html.parser")
    rail = soup.select_one(".rd-rail")
    assert rail is not None
    primary = rail.select("nav > ul.rd-nav .rd-nav__link")
    footer = rail.select(".rd-rail__footer .rd-nav__link")
    assert len(primary) == 4, f"expected 4 primary rail items, got {len(primary)}"
    # T-D47: only Settings in the footer nav; account block = email + Sign out.
    labels = [a.get_text(strip=True) for a in footer]
    assert labels == ["Settingsg s"], labels
    assert rail.select_one('.rd-rail__account form[action="/auth/logout"]') is not None


def test_shell_slots_present(client: TestClient) -> None:
    """Rising Dough v2 base shell exposes drawer-root + modal-root + toast-root."""
    r = client.get("/today")
    soup = BeautifulSoup(r.text, "html.parser")
    assert soup.find(id="drawer-root") is not None
    assert soup.find(id="modal-root") is not None
    assert soup.find(id="toast-root") is not None
    assert soup.select_one(".rd-rail") is not None
    assert soup.select_one(".rd-main") is not None
