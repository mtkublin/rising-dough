"""T-D55 — authenticated responses are ``no-store`` (ADR-0078 §2)."""

from __future__ import annotations

import pytest
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

pytestmark = pytest.mark.integration

AUTHENTICATED_GETS = [
    "/today",
    "/ledger",
    "/budget",
    "/accounts",
    "/settings/security",
]


@pytest.mark.parametrize("path", AUTHENTICATED_GETS)
def test_authenticated_pages_are_no_store(client: TestClient, path: str) -> None:
    r = client.get(path, follow_redirects=False)
    assert r.status_code < 400
    assert r.headers["cache-control"] == "no-store"


def test_htmx_partial_is_no_store(client: TestClient) -> None:
    r = client.get("/ledger", headers={"HX-Request": "true"})
    assert r.headers["cache-control"] == "no-store"


def test_json_route_is_no_store(client: TestClient) -> None:
    r = client.get("/debug/audit-tail")
    assert r.headers["cache-control"] == "no-store"


def test_weaker_route_value_is_overwritten(client: TestClient) -> None:
    app = client.app

    @app.get("/__t_d55_weak")  # type: ignore[attr-defined,untyped-decorator]
    def _weak() -> JSONResponse:
        return JSONResponse({}, headers={"Cache-Control": "max-age=600"})

    r = client.get("/__t_d55_weak")
    assert r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", ["/health", "/ready", "/auth/login"])
def test_unauthenticated_paths_unchanged(anon_client: TestClient, path: str) -> None:
    r = anon_client.get(path, follow_redirects=False)
    assert "no-store" not in r.headers.get("cache-control", "")


def test_static_assets_stay_cacheable(client: TestClient) -> None:
    r = client.get("/static/app.css")
    assert r.status_code == 200
    assert "no-store" not in r.headers.get("cache-control", "")


def test_logout_sends_clear_site_data(client: TestClient) -> None:
    r = client.post("/auth/logout", follow_redirects=False)
    assert r.headers["clear-site-data"] == '"cache", "storage"'
