"""T-D50 / ADR-0077: `/` redirects to Today; shell + navigation on /today."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.ui_map import _html, shell


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
    brand = _html.resolve_one(client.get("/today").text, shell.brand_link)
    assert brand["href"] == "/today"


def test_nav_links_present(client: TestClient) -> None:
    """Rising Dough v2 rail — ADR-0051 §1 IA.

    Nav collapses v1 Budget + Forecast + Analytics into /plan (tabs).
    Legacy /transactions, /planned, /recurring still 302 but the rail no
    longer links to them directly.
    """
    r = client.get("/today")
    assert r.status_code == 200
    hrefs = {a["href"] for a in _html.resolve(r.text, shell.nav_links)}
    for path in ("/today", "/ledger", "/plan", "/accounts", "/settings"):
        assert path in hrefs, f"nav missing {path}"
    assert "/transactions" not in hrefs
    assert "/budget" not in hrefs
    assert "/forecast" not in hrefs


def test_nav_has_four_primary_items_plus_settings(client: TestClient) -> None:
    html = client.get("/today").text
    for name in ("Today", "Ledger", "Plan", "Accounts", "Settings"):
        assert _html.count(html, shell.nav_link(name)) == 1, name
    assert _html.count(html, shell.nav_links) == 5, "4 primary rail items + Settings"
    # T-D47: account block = Sign out form posting to /auth/logout.
    sign_outs = _html.resolve(html, shell.sign_out)  # rail + mobile account nav
    assert sign_outs
    for button in sign_outs:
        form = button.find_parent("form")
        assert form is not None
        assert form["action"] == "/auth/logout"


def test_shell_slots_present(client: TestClient) -> None:
    """Rising Dough v2 base shell exposes drawer-root + modal-root + toast-root."""
    html = client.get("/today").text
    for slot in (shell.drawer_root, shell.modal_root, shell.toast_root, shell.main):
        assert _html.exists(html, slot)
