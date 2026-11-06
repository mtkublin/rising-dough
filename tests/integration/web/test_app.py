"""T-030 skeleton: healthz, dev index, static assets, Jinja env, HTMX helpers."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from bs4 import BeautifulSoup
from fastapi import Request
from fastapi.responses import Response
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.web.app import create_app
from budget_planner.web.htmx import is_htmx, trigger, trigger_from_iterable
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
    assert "htmx.org" in body
    # T-R50 — Plotly removed per ADR-0054; SVG charts are server-rendered now.
    assert "tailwind" in body
    soup = BeautifulSoup(body, "html.parser")
    assert soup.find("main", id="main") is not None
    assert soup.find("a", href="#main") is not None


def test_static_css_is_served(client: TestClient) -> None:
    r = client.get("/static/app.css")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/css")
    assert "--surface" in r.text


def test_jinja_filters_registered() -> None:
    env = build_jinja_env(_settings())
    for name in ("money", "date_fmt", "dt_local", "direction_badge"):
        assert name in env.filters
    tmpl = env.from_string(
        "{{ 123400|money('PLN') }} | {{ '2026-01-02'|date_fmt }} | "
        "{{ '2026-01-02T10:00:00'|dt_local }} | {{ 'income'|direction_badge }}"
    )
    out = tmpl.render()
    assert "1,234.00 PLN" in out
    assert "2026-01-02" in out
    assert "Income" in out


def test_dt_local_uses_display_timezone() -> None:
    env = build_jinja_env(Settings(_env_file=None, display_timezone="UTC"))
    tmpl = env.from_string("{{ '2026-01-02T10:00:00'|dt_local('%H:%M') }}")
    assert tmpl.render() == "10:00"


def test_jinja_autoescape_prevents_xss() -> None:
    env = build_jinja_env(_settings())
    tmpl = env.from_string("{{ val }}")
    out = tmpl.render(val="<script>alert(1)</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_trigger_sets_hx_trigger_header() -> None:
    resp = Response()
    trigger(resp, "balance-stale", "forecast-stale")
    hx = resp.headers["HX-Trigger"]
    data = json.loads(hx)
    assert data == {"balance-stale": True, "forecast-stale": True}


def test_trigger_no_events_noop() -> None:
    resp = Response()
    trigger(resp)
    assert "HX-Trigger" not in resp.headers


def test_trigger_from_iterable() -> None:
    resp = Response()
    trigger_from_iterable(resp, ["a", "b"])
    assert json.loads(resp.headers["HX-Trigger"]) == {"a": True, "b": True}


def test_is_htmx_detects_header() -> None:
    req = MagicMock(spec=Request)
    req.headers = {}
    assert is_htmx(req) is False
    req.headers = {"HX-Request": "true"}
    assert is_htmx(req) is True
    req.headers = {"HX-Request": "false"}
    assert is_htmx(req) is False


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


def test_direction_badge_renders_all_variants() -> None:
    env = build_jinja_env(_settings())
    tmpl = env.from_string(
        "{{ 'income'|direction_badge }}{{ 'expense'|direction_badge }}"
        "{{ 'transit'|direction_badge }}{{ 'adjustment'|direction_badge }}"
    )
    out = tmpl.render()
    assert out.count("pill ") == 4
    assert "pill-income" in out
    assert "pill-expense" in out
    assert "pill-transit" in out
    assert "pill-adjust" in out


def test_direction_badge_handles_none() -> None:
    env = build_jinja_env(_settings())
    tmpl = env.from_string("[{{ none|direction_badge }}]")
    assert tmpl.render() == "[]"


def test_money_filter_handles_none() -> None:
    env = build_jinja_env(_settings())
    tmpl = env.from_string("[{{ none|money('PLN') }}]")
    assert tmpl.render() == "[]"


def test_date_fmt_handles_none_and_bad_input() -> None:
    env = build_jinja_env(_settings())
    assert env.from_string("[{{ none|date_fmt }}]").render() == "[]"
    assert env.from_string("[{{ 'nope'|date_fmt }}]").render() == "[nope]"


def test_dt_local_handles_none_and_bad_input() -> None:
    env = build_jinja_env(_settings())
    assert env.from_string("[{{ none|dt_local }}]").render() == "[]"
    assert env.from_string("[{{ 'nope'|dt_local }}]").render() == "[nope]"


def test_csrf_token_global_is_empty_in_v1() -> None:
    env = build_jinja_env(_settings())
    assert env.from_string("{{ csrf_token() }}").render() == ""
