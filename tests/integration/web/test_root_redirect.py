"""T-D50 / ADR-0077: `/` redirects to Today; shell + navigation on /today."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.ui_map import _html, rd_shell, shell


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
    """Rising Dough v2 top nav (ADR-0051 section 1 IA): four primary items, Settings in the header.

    Budget, Forecast and Analytics are tabs of /plan; the nav does not link to them.
    """
    r = client.get("/today")
    assert r.status_code == 200
    hrefs = {a["href"] for a in _html.resolve(r.text, rd_shell.nav_links)}
    assert hrefs == {"/today", "/ledger", "/plan", "/accounts"}
    assert _html.resolve_one(r.text, rd_shell.settings_link)["href"] == "/settings"


def test_nav_has_four_primary_items_plus_settings(client: TestClient) -> None:
    html = client.get("/today").text
    for name in ("today", "ledger", "plan", "accounts"):
        assert _html.count(html, rd_shell.nav_link(name)) == 1, name
        assert _html.count(html, rd_shell.tab_link(name)) == 1, name
    assert _html.count(html, rd_shell.nav_links) == 4, "4 primary items; Settings is in the header"
    # T-D47: account block = Sign out form posting to /auth/logout.
    sign_outs = _html.resolve(html, rd_shell.sign_out)
    assert len(sign_outs) == 1
    form = sign_outs[0].find_parent("form")
    assert form is not None
    assert form["action"] == "/auth/logout"


def test_shell_slots_present(client: TestClient) -> None:
    """Rising Dough v2 base shell exposes drawer-root + modal-root + toast-root."""
    html = client.get("/today").text
    for slot in (shell.drawer_root, shell.modal_root, shell.toast_root, shell.main):
        assert _html.exists(html, slot)
