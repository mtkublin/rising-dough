"""Integration tests for /today rendering (T-R40, ADR-0056 section 3).

Status codes, window range and auth are in ``tests/contract/test_today.py``;
the rendered values are checked here through the UI map.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.ui_map import _html, today, today_app


def test_today_renders_heading(client: TestClient) -> None:
    assert _html.exists(client.get("/today").text, today.heading)


def test_afford_preview_shows_per_day_figure(client: TestClient) -> None:
    html = client.get("/today/afford?amount=10000").text
    per_day = _html.text_of(html, today_app.afford_per_day)
    assert per_day  # a formatted amount
    assert _html.exists(html, today_app.afford_delta)


def test_afford_preview_without_amount_has_no_delta(client: TestClient) -> None:
    html = client.get("/today/afford?amount=0").text
    assert _html.exists(html, today_app.afford_per_day)
    assert not _html.exists(html, today_app.afford_delta)


def test_afford_delta_is_signed_per_day(client: TestClient) -> None:
    # Spending can only lower the per-day budget, so the delta is negative or zero.
    delta = _html.text_of(client.get("/afford?amount=100.00").text, today_app.afford_delta)
    assert delta.endswith("/ day")
    assert delta.startswith(("-", "+"))
