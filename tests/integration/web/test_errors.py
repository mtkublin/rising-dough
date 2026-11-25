"""T-051: exception handlers + request id middleware integration tests.

Covers:
- Each domain exception is mapped to the right HTTP status.
- HTMX requests get a flash fragment with the correct ARIA shape.
- Browser (non-HTMX) requests get a full-page error template.
- 500-class errors log a correlation id and echo it to the response header.
- `X-Request-Id` middleware either honours or generates an id per request.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.domain.errors import (
    ConflictError,
    NotFoundError,
    ServiceError,
    ValidationError,
)
from budget_planner.web.app import create_app
from tests.auth_support import login_cookie
from tests.ui_map import _html, errors
from tests.ui_map.locator import by_id, role


@pytest.fixture
def error_client(tmp_path: Path) -> Iterator[TestClient]:
    """TestClient with a router that deliberately raises each error type."""
    db_url = f"sqlite:///{(tmp_path / 'errors.sqlite').as_posix()}"
    cfg = Settings(_env_file=None, database_url=db_url)
    conn = get_connection(cfg)
    try:
        apply_migrations(conn)
    finally:
        conn.close()
    app = create_app(settings=cfg)
    router = APIRouter()

    @router.get("/_boom/not-found")
    def _nf() -> None:
        raise NotFoundError(entity="transaction", entity_id=42)

    @router.get("/_boom/conflict")
    def _cf() -> None:
        raise ConflictError(message="protected row")

    @router.get("/_boom/validation")
    def _vf() -> None:
        raise ValidationError(fields={"amount": "amount must be positive"})

    @router.get("/_boom/service")
    def _svc() -> None:
        raise ServiceError(message="downstream unavailable")

    @router.get("/_boom/unhandled")
    def _un() -> None:
        raise RuntimeError("kaboom")

    @router.post("/_boom/unhandled-write")
    def _unw() -> None:
        raise RuntimeError("kaboom")

    app.include_router(router)
    cookie = login_cookie(cfg)
    with TestClient(app, raise_server_exceptions=False) as c:
        c.cookies.set(*cookie)
        yield c


def test_not_found_browser_renders_404_page(error_client: TestClient) -> None:
    r = error_client.get("/_boom/not-found")
    assert r.status_code == 404
    assert _html.text_of(r.text, errors.heading) == "Not found"
    assert "exist or was removed" in _html.text_of(r.text, errors.main)
    # Request id echoed by middleware.
    assert r.headers.get("X-Request-Id")


def test_not_found_htmx_renders_flash_fragment(error_client: TestClient) -> None:
    r = error_client.get("/_boom/not-found", headers={"HX-Request": "true"})
    assert r.status_code == 404
    region = _html.resolve_one(r.text, by_id("flash-region-assertive"))
    assert region["aria-live"] == "assertive"
    assert region["hx-swap-oob"] == "true"
    assert "\N{BLACK UP-POINTING TRIANGLE} Transaction not found" in region.get_text()


def test_conflict_browser_renders_409_page(error_client: TestClient) -> None:
    r = error_client.get("/_boom/conflict")
    assert r.status_code == 409
    heading = _html.text_of(r.text, errors.heading)
    assert heading == "Changed elsewhere"
    assert "protected row" in _html.text_of(r.text, errors.main)


def test_conflict_htmx_renders_polite_flash(error_client: TestClient) -> None:
    r = error_client.get("/_boom/conflict", headers={"HX-Request": "true"})
    assert r.status_code == 409
    region = _html.resolve_one(r.text, by_id("flash-region"))
    assert region["aria-live"] == "polite"
    assert "protected row" in region.get_text()


def test_validation_browser_renders_422_page(error_client: TestClient) -> None:
    r = error_client.get("/_boom/validation")
    assert r.status_code == 422
    assert "save that" in _html.text_of(r.text, errors.heading)
    assert "amount" in _html.text_of(r.text, errors.main)


def test_validation_htmx_renders_error_flash(error_client: TestClient) -> None:
    r = error_client.get("/_boom/validation", headers={"HX-Request": "true"})
    assert r.status_code == 422
    assert "amount must be positive" in _html.text_of(r.text, by_id("flash-region-assertive"))


def test_service_error_browser_renders_500_with_request_id(
    error_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="budget_planner.web"):
        r = error_client.get("/_boom/service")
    assert r.status_code == 500
    rid = r.headers.get("X-Request-Id")
    assert rid
    main_text = _html.text_of(r.text, errors.main)
    assert "downstream unavailable" in main_text
    assert rid in main_text
    # Correlation id present in log context.
    found = any(getattr(rec, "request_id", None) == rid for rec in caplog.records)
    assert found, "request_id missing from log context"


def test_service_error_htmx_renders_flash_with_reference(error_client: TestClient) -> None:
    r = error_client.get("/_boom/service", headers={"HX-Request": "true"})
    assert r.status_code == 500
    flash = _html.text_of(r.text, by_id("flash-region-assertive"))
    assert "Reference:" in flash
    rid = r.headers["X-Request-Id"]
    assert rid in flash


def test_failed_htmx_write_flashes_the_handoff_copy_with_retry(error_client: TestClient) -> None:
    """handoff today--flash: a failed save keeps the form, offers retry, tooltip holds the id."""
    r = error_client.post("/_boom/unhandled-write", headers={"HX-Request": "true"})
    assert r.status_code == 500
    rid = r.headers["X-Request-Id"]
    flash = _html.text_of(r.text, by_id("flash-region-assertive"))
    assert "\u25b2 Couldn\u2019t save. Your changes are still in the form." in flash
    assert _html.exists(r.text, role("button", "retry").inside(by_id("flash-region-assertive")))
    assert f"Reference: {rid}" in flash  # also a visually hidden text for keyboard and touch users


def test_unhandled_exception_falls_back_to_500(
    error_client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="budget_planner.web"):
        r = error_client.get("/_boom/unhandled")
    assert r.status_code == 500
    assert _html.text_of(r.text, errors.heading) == "Something broke"
    rid = r.headers["X-Request-Id"]
    assert rid
    assert any(getattr(rec, "request_id", None) == rid for rec in caplog.records)


def test_request_id_middleware_honours_incoming_header(error_client: TestClient) -> None:
    r = error_client.get("/_boom/not-found", headers={"X-Request-Id": "test-trace-1234"})
    assert r.headers["X-Request-Id"] == "test-trace-1234"


def test_request_id_middleware_generates_fresh_id(client: TestClient) -> None:
    """Default client has no custom routes; /health round-trip still has an id."""
    r = client.get("/health")
    rid = r.headers.get("X-Request-Id")
    assert rid and len(rid) == 12  # uuid4().hex[:12]


def test_validation_inline_form_render_on_transactions_post(client: TestClient) -> None:
    """End-to-end: posting an invalid transaction re-renders the form fragment,
    not a redirect, with the amount field marked invalid. Covers the inline-form
    validation path promised by T-051."""
    r = client.post(
        "/transactions",
        data={
            "operation_date": "2026-10-24",
            "category_id": "999999",  # unknown
            "account_id": "999999",
            "amount": "not-a-number",
        },
        headers={"HX-Request": "true"},
    )
    assert r.status_code == 422
    # Form partial re-renders inline (no Location redirect).
    assert "Location" not in r.headers
    # Server-side error listing is present.
    assert _html.error_lines(r.text) == {
        "catpick-new-entry-error": "▲ unknown category",
        "field-account_id-error": "▲ unknown account",
    }


@pytest.mark.parametrize(
    ("path", "status", "expected"),
    [
        ("/_boom/not-found", 404, ("flash-region-assertive", "assertive", "Transaction not found")),
        ("/_boom/conflict", 409, ("flash-region", "polite", "protected row")),
        ("/_boom/service", 500, ("flash-region-assertive", "assertive", "downstream unavailable")),
    ],
)
def test_htmx_error_uses_the_rd_flash_fragment(
    error_client: TestClient, path: str, status: int, expected: tuple[str, str, str]
) -> None:
    region, live, text = expected
    r = error_client.get(path, headers={"HX-Request": "true"})
    assert r.status_code == status
    live_region = _html.resolve_one(r.text, by_id(region))
    assert live_region["aria-live"] == live
    assert live_region["hx-swap-oob"] == "true"
    flash = _html.resolve_one(r.text, errors.alert.inside(by_id(region)))
    assert flash["class"] == ["rd-flash", "rd-flash--error"]
    assert f"▲ {text}" in flash.get_text()
    close = _html.resolve_one(r.text, role("button", "Dismiss").inside(by_id(region)))
    assert close["data-js"] == "flash-close"
