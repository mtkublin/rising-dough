"""T-030 skeleton: healthz, dev index, static assets, Jinja env, HTMX helpers."""

from __future__ import annotations

import importlib
import json
import pkgutil

import pytest
from bs4 import BeautifulSoup
from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.web import routers as routers_pkg
from budget_planner.web.app import create_app
from budget_planner.web.htmx import Event, trigger
from budget_planner.web.templating import build_jinja_env


def _settings() -> Settings:
    return Settings(_env_file=None)


def test_health_returns_ok(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert "version" in r.json()


def test_today_renders_shell(client: TestClient) -> None:
    r = client.get("/today")
    assert r.status_code == 200
    body = r.text
    assert '<html lang="en"' in body
    # ADR-0113 — htmx is vendored (CSP-compatible), never loaded from a CDN.
    assert "/static/vendor/htmx-" in body
    assert "unpkg.com" not in body
    # T-R50 — Plotly removed per ADR-0054; SVG charts are server-rendered now.
    soup = BeautifulSoup(body, "html.parser")
    sheets = [str(link.get("href", "")) for link in soup.find_all("link", rel="stylesheet")]
    assert any("rd/css/app.bundle.css" in href for href in sheets)
    assert soup.find("main", id="main") is not None
    assert soup.find("a", href="#main") is not None


def test_static_css_is_served(client: TestClient) -> None:
    r = client.get("/static/rd/css/app.bundle.css")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/css")
    assert "--color-ground" in r.content.decode()  # CSS asset body, not markup


def test_jinja_filters_registered() -> None:
    env = build_jinja_env(_settings())
    for name in ("money", "date_fmt"):
        assert name in env.filters
    tmpl = env.from_string("{{ 123400|money('PLN') }} | {{ '2026-01-02'|date_fmt }}")
    out = tmpl.render()
    assert "1,234.00 PLN" in out
    assert "2026-01-02" in out


def test_jinja_autoescape_prevents_xss() -> None:
    env = build_jinja_env(_settings())
    tmpl = env.from_string("{{ val }}")
    out = tmpl.render(val="<script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_trigger_sets_hx_trigger_header() -> None:
    resp = Response()
    trigger(resp, Event.BALANCE_STALE, Event.FORECAST_STALE)
    hx = resp.headers["HX-Trigger"]
    data = json.loads(hx)
    assert data == {"balance-stale": True, "forecast-stale": True}


def test_trigger_no_events_noop() -> None:
    resp = Response()
    trigger(resp)
    assert "HX-Trigger" not in resp.headers


def test_create_app_respects_settings() -> None:
    cfg = Settings(_env_file=None, base_currency="EUR")
    app = create_app(settings=cfg)
    assert app.state.settings.base_currency == "EUR"
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200


def test_host_defaults_to_loopback() -> None:
    cfg = Settings(_env_file=None)
    assert cfg.bind_host == "127.0.0.1"


def test_host_rejects_public_bind() -> None:
    with pytest.raises(ValueError, match="loopback"):
        Settings(_env_file=None, bind_host="0.0.0.0")  # noqa: S104 — asserting we reject it


def test_money_filter_handles_none() -> None:
    env = build_jinja_env(_settings())
    tmpl = env.from_string("[{{ none|money('PLN') }}]")
    assert tmpl.render() == "[]"


def test_date_fmt_handles_none_and_bad_input() -> None:
    env = build_jinja_env(_settings())
    assert env.from_string("[{{ none|date_fmt }}]").render() == "[]"
    assert env.from_string("[{{ 'nope'|date_fmt }}]").render() == "[nope]"


_EXPECTED_ROUTER_MODULES = frozenset(
    {
        "accounts",
        "auth",
        "budget",
        "categories",
        "debug",
        "dev_components",
        "forecast",
        "health",
        "ledger",
        "plan",
        "planned",
        "recurring",
        "settings",
        "settings_password",
        "settings_security",
        "settings_users",
        "setup",
        "today",
        "transactions",
    }
)


def _included_routers(app: FastAPI) -> list[object]:
    return [r.original_router for r in app.routes if hasattr(r, "original_router")]


def test_every_router_module_is_registered() -> None:
    """T-Q257 (Q-073): the router set is exact and every module's router is mounted once."""
    on_disk = {
        m.name for m in pkgutil.iter_modules(routers_pkg.__path__) if not m.name.startswith("_")
    }
    assert on_disk == _EXPECTED_ROUTER_MODULES

    included = _included_routers(
        create_app(Settings(_env_file=None, env="dev", cookie_secret="x" * 48))
    )
    for name in sorted(on_disk):
        module = importlib.import_module(f"budget_planner.web.routers.{name}")
        assert module.router.routes, name
        assert sum(1 for r in included if r is module.router) == 1, name
    assert len(included) == len(on_disk)


def test_dev_components_router_is_not_registered_in_production() -> None:
    included = _included_routers(
        create_app(
            Settings(
                _env_file=None,
                env="production",
                cookie_secret="x" * 48,
                webauthn_rp_id="example.com",
                webauthn_origin="https://example.com",
            )
        )
    )
    dev = importlib.import_module("budget_planner.web.routers.dev_components")
    assert all(r is not dev.router for r in included)
    assert len(included) == len(_EXPECTED_ROUTER_MODULES) - 1
