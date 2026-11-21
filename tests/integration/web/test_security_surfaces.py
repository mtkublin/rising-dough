"""T-Q254: 500 headers, app-owned CSP nonce, Host allow-list, prod surfaces off (ADR-0036)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.web.app import create_app
from budget_planner.web.rendering import render_str

_HEADERS = (
    "Strict-Transport-Security",
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Referrer-Policy",
    "Permissions-Policy",
)


def _prod_settings(tmp_path: Path) -> Settings:
    db = tmp_path / "prod_sim.db"
    cfg = Settings(
        _env_file=None,
        env="production",
        cookie_secret="x" * 32,
        webauthn_rp_id="budget.example.test",
        webauthn_origin="https://budget.example.test",
        database_url=f"sqlite:///{db.as_posix()}",
        admin_email="admin@prodsim.test",
        admin_initial_password="prodsim-only",  # noqa: S106  # pragma: allowlist secret
        trusted_hosts=("budget.example.test",),
    )
    conn = get_connection(cfg)
    try:
        apply_migrations(conn)
    finally:
        conn.close()
    return cfg


@pytest.fixture
def prod_client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(settings=_prod_settings(tmp_path))
    with TestClient(app, base_url="https://budget.example.test") as c:
        yield c


def test_forced_500_carries_all_security_headers_and_no_store(
    _migrated: Settings, session_cookie: tuple[str, str]
) -> None:
    app = create_app(settings=_migrated)
    router = APIRouter()

    @router.get("/_boom")
    def _boom() -> None:
        raise RuntimeError("kaboom")

    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as c:
        c.cookies.set(*session_cookie)
        r = c.get("/_boom")
    assert r.status_code == 500
    for name in _HEADERS:
        assert name in r.headers, name
    assert r.headers["Cache-Control"] == "no-store"
    assert "Content-Security-Policy" in r.headers


def test_client_supplied_nonce_is_ignored(
    _migrated: Settings, session_cookie: tuple[str, str]
) -> None:
    app = create_app(settings=_migrated)

    @app.get("/_test/nonce", response_class=PlainTextResponse)
    def _echo(request: Request) -> PlainTextResponse:
        return PlainTextResponse(render_str(request, "{{ csp_nonce }}"), media_type="text/html")

    with TestClient(app) as c:
        c.cookies.set(*session_cookie)
        r = c.get("/_test/nonce", headers={"X-CSP-Nonce": "attacker"})
    assert r.text
    assert r.text != "attacker"
    csp = r.headers["Content-Security-Policy"]
    assert f"'nonce-{r.text}'" in csp
    assert "attacker" not in csp
    assert re.search(r"script-src 'self' 'nonce-[\w-]+'", csp)


def test_non_allowed_host_is_rejected(prod_client: TestClient) -> None:
    r = prod_client.get("/health", headers={"Host": "evil.example.com"})
    assert r.status_code == 400
    assert "X-Frame-Options" in r.headers


def test_allowed_and_loopback_hosts_pass(prod_client: TestClient) -> None:
    assert prod_client.get("/health").status_code == 200
    assert prod_client.get("/health", headers={"Host": "127.0.0.1:8000"}).status_code == 200


def test_docs_and_openapi_are_not_routed_in_production(prod_client: TestClient) -> None:
    app = prod_client.app
    paths = {getattr(r, "path", "") for r in app.routes}  # type: ignore[attr-defined]  # test-only introspection
    assert not paths & {"/docs", "/openapi.json", "/dev/components"}
    assert app.docs_url is None  # type: ignore[attr-defined]  # test-only introspection
    assert app.openapi_url is None  # type: ignore[attr-defined]  # test-only introspection


def test_docs_enabled_in_dev(_migrated: Settings) -> None:
    app = create_app(settings=_migrated)
    assert app.docs_url == "/docs"
    assert app.openapi_url == "/openapi.json"
