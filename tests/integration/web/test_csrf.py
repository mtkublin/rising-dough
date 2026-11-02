"""T-D08 — CSRF middleware integration tests (ADR-0033 §4).

Four scenarios:

1. A GET on any live route mints ``__Host-csrf`` and surfaces it as a
   response cookie.
2. A mutating request *without* the ``X-CSRF-Token`` header (and without
   a form token) is rejected with ``403 {"detail": "invalid_csrf"}``.
3. A mutating request with a matching cookie + header succeeds.
4. A mutating request with a mismatched header is rejected with ``403``.

The tests build a dedicated FastAPI app with a tiny POST route so the
assertions do not depend on the shape of real routers (accounts,
categories, …). The shared ``client`` fixture auto-primes the token;
these tests deliberately bypass it to exercise the raw middleware.
"""

from __future__ import annotations

import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import Request
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.web.app import create_app
from budget_planner.web.middleware.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_FORM_FIELD,
    CSRF_HEADER_NAME,
)
from budget_planner.web.rendering import render_str


@pytest.fixture
def raw_client() -> Iterator[TestClient]:
    """Fresh app + raw TestClient — no auto-prime, no auto-header."""
    cfg = Settings(_env_file=None)
    app = create_app(settings=cfg)

    @app.post("/_test/echo", response_class=PlainTextResponse)
    def _echo() -> PlainTextResponse:
        return PlainTextResponse("ok")

    with TestClient(app, base_url="https://testserver") as c:
        yield c


def test_get_sets_csrf_cookie(raw_client: TestClient) -> None:
    """First GET on any route attaches ``__Host-csrf`` to the response."""
    r = raw_client.get("/health")
    assert r.status_code == 200
    jar = r.cookies
    assert CSRF_COOKIE_NAME in jar
    token = jar[CSRF_COOKIE_NAME]
    assert token
    # URL-safe base64 → alphanumeric + ``-_``.
    assert all(c.isalnum() or c in "-_" for c in token)


def test_post_without_token_is_rejected(raw_client: TestClient) -> None:
    """POST with no cookie, no header → 403 invalid_csrf."""
    # Clear any auto-stored cookies to simulate a cold client.
    raw_client.cookies.clear()
    r = raw_client.post("/_test/echo")
    assert r.status_code == 403
    assert r.json() == {"detail": "missing_cookie"}


def test_post_with_matching_header_is_accepted(raw_client: TestClient) -> None:
    """POST with a matching cookie + header succeeds."""
    # Priming GET — stores cookie in the client's jar.
    r0 = raw_client.get("/health")
    token = r0.cookies[CSRF_COOKIE_NAME]

    r = raw_client.post("/_test/echo", headers={CSRF_HEADER_NAME: token})
    assert r.status_code == 200
    assert r.text == "ok"


def test_post_with_mismatched_header_is_rejected(raw_client: TestClient) -> None:
    """POST with a cookie but a wrong header → 403."""
    r0 = raw_client.get("/health")
    assert CSRF_COOKIE_NAME in r0.cookies

    r = raw_client.post("/_test/echo", headers={CSRF_HEADER_NAME: "not-the-token"})
    assert r.status_code == 403
    assert r.json() == {"detail": "invalid_csrf"}


def test_post_with_matching_form_field_is_accepted(raw_client: TestClient) -> None:
    """Non-HTMX form POSTs can submit the token via ``_csrf_token`` field."""
    r0 = raw_client.get("/health")
    token = r0.cookies[CSRF_COOKIE_NAME]

    r = raw_client.post(
        "/_test/echo",
        data={CSRF_FORM_FIELD: token},
    )
    assert r.status_code == 200


def test_exempt_path_allows_post_without_token(raw_client: TestClient) -> None:
    """``/health`` is exempt — POST without a token should not 403.

    The route only answers GET so FastAPI returns ``405``; the important
    bit is that it is **not** a 403 from the CSRF layer.
    """
    raw_client.cookies.clear()
    r = raw_client.post("/health")
    assert r.status_code != 403


def test_cookie_is_stable_across_requests(raw_client: TestClient) -> None:
    """Once the cookie is minted it is reused — the middleware does not
    churn the token on every request."""
    r0 = raw_client.get("/health")
    token0 = r0.cookies[CSRF_COOKIE_NAME]

    r1 = raw_client.get("/health")
    # Second GET should not re-set the cookie (there was already one in
    # the jar), so the Set-Cookie header is absent on r1.
    assert CSRF_COOKIE_NAME not in r1.cookies
    # And the stored jar cookie is unchanged.
    assert raw_client.cookies[CSRF_COOKIE_NAME] == token0


def test_dev_env_drops_secure_flag() -> None:
    """``env=dev`` suppresses the ``Secure`` attribute for local HTTP."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        cfg = Settings(_env_file=None, env="dev")
    app = create_app(settings=cfg)
    with TestClient(app) as c:
        r = c.get("/health")
    set_cookie = r.headers.get("set-cookie", "")
    assert CSRF_COOKIE_NAME in set_cookie
    assert "Secure" not in set_cookie


def test_production_env_sets_secure_flag(tmp_path: Path) -> None:
    """``env=production`` keeps ``Secure`` on the cookie."""
    db = tmp_path / "prod_sim.db"
    cfg = Settings(
        _env_file=None,
        env="production",
        cookie_secret="x" * 32,
        database_url=f"sqlite:///{db.as_posix()}",
    )
    app = create_app(settings=cfg)
    with TestClient(app, base_url="https://testserver") as c:
        r = c.get("/health")
    set_cookie = r.headers.get("set-cookie", "")
    assert CSRF_COOKIE_NAME in set_cookie
    assert "Secure" in set_cookie
    assert "samesite=lax" in set_cookie.lower()


def _app_with_csrf_echo() -> TestClient:
    """Build an app that echoes ``csrf_token`` via Jinja."""
    cfg = Settings(_env_file=None)
    app = create_app(settings=cfg)

    @app.get("/_test/csrf-echo", response_class=PlainTextResponse)
    def _csrf_echo(request: Request) -> PlainTextResponse:
        return PlainTextResponse(render_str(request, "token:{{ csrf_token }}"))

    return TestClient(app, base_url="https://testserver")


def test_csrf_token_available_in_jinja_context() -> None:
    """``request.state.csrf_token`` is surfaced to templates as ``csrf_token``."""
    client = _app_with_csrf_echo()
    with client:
        r = client.get("/_test/csrf-echo")
    assert r.status_code == 200, r.text
    assert r.text.startswith("token:")
    assert r.text != "token:"
