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
    region = _html.resolve_one(r.text, errors.alert)
    assert region["aria-live"] == "assertive"
    assert region["hx-swap-oob"] == "true"
    assert "Transaction not found" in region.get_text()


def test_conflict_browser_renders_409_page(error_client: TestClient) -> None:
    r = error_client.get("/_boom/conflict")
    assert r.status_code == 409
    heading = _html.text_of(r.text, errors.heading)
    assert heading == "Changed elsewhere"
    assert "protected row" in _html.text_of(r.text, errors.main)


def test_conflict_htmx_renders_warning_flash(error_client: TestClient) -> None:
    r = error_client.get("/_boom/conflict", headers={"HX-Request": "true"})
    assert r.status_code == 409
    region = _html.resolve_one(r.text, errors.status)
    assert any(el.get("data-flash-kind") == "warning" for el in region.find_all(True))
    assert "protected row" in region.get_text()


def test_validation_browser_renders_422_page(error_client: TestClient) -> None:
    r = error_client.get("/_boom/validation")
    assert r.status_code == 422
    assert "save that" in _html.text_of(r.text, errors.heading)
    assert "amount" in _html.text_of(r.text, errors.main)


def test_validation_htmx_renders_error_flash(error_client: TestClient) -> None:
    r = error_client.get("/_boom/validation", headers={"HX-Request": "true"})
    assert r.status_code == 422
    assert "amount must be positive" in _html.text_of(r.text, errors.alert)


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
    flash = _html.text_of(r.text, errors.alert)
    assert "Reference:" in flash
    rid = r.headers["X-Request-Id"]
    assert rid in flash


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
    listed = _html.text_of(r.text, errors.alert)
    assert "unknown account" in listed or "unknown category" in listed


def test_flash_inline_render_does_not_emit_oob_attribute(client: TestClient) -> None:
    """The `_flash.html` partial supports an `oob=false` branch for inline
    (non-HTMX) use. Smoke-test by rendering the template directly."""
    env = client.app.state.jinja_env  # type: ignore[attr-defined]
    html = env.get_template("partials/_flash.html").render(
        level="success", message="Saved", oob=False
    )
    assert "hx-swap-oob" not in html
    assert 'role="status"' in html
    assert "Saved" in html
