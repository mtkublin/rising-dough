"""T-D07 — Security headers middleware + CSP nonce propagation.

Covers ADR-0036 §3 (nonce flow) and ADR-0033 §5 (middleware chain order).
The middleware adds five baseline headers when the downstream response does
not already set them and propagates the Caddy-supplied ``X-CSP-Nonce`` into
``request.state.csp_nonce`` so Jinja templates can embed it. In the absence
of a proxy header (dev / tests) the middleware mints a fresh nonce per
request.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.web.app import create_app
from budget_planner.web.rendering import render_str

_EXPECTED_HEADERS: dict[str, str] = {
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), interest-cohort=()",
}


def test_security_headers_present_on_health(client: TestClient) -> None:
    """Every baseline response header is set with the ADR-0036 value."""
    r = client.get("/health")
    assert r.status_code == 200
    for name, value in _EXPECTED_HEADERS.items():
        assert r.headers.get(name) == value, (
            f"missing or mismatched header {name!r}: got {r.headers.get(name)!r}"
        )


def test_security_headers_include_request_id_header(client: TestClient) -> None:
    """RequestId middleware still runs; both middlewares cohabit cleanly."""
    r = client.get("/health")
    assert r.status_code == 200
    assert "X-Request-Id" in r.headers


def _app_with_echo_route(cfg: Settings, cookie: tuple[str, str]) -> TestClient:
    """Build an app with a tiny route that echoes the Jinja csp_nonce value.

    The route is behind ``AuthRequiredMiddleware`` (T-D02b), so the client
    carries a real session cookie for the migrated temp DB.
    """
    app = create_app(settings=cfg)

    @app.get("/_test/nonce", response_class=PlainTextResponse)
    def _nonce_echo(request: Request) -> PlainTextResponse:
        rendered = render_str(request, "nonce:{{ csp_nonce }}")
        return PlainTextResponse(rendered)

    client = TestClient(app)
    client.cookies.set(*cookie)
    return client


def test_csp_nonce_from_header_reaches_jinja_context(
    _migrated: Settings, session_cookie: tuple[str, str]
) -> None:
    """When Caddy forwards ``X-CSP-Nonce``, Jinja templates see the same value."""
    client = _app_with_echo_route(_migrated, session_cookie)
    with client:
        r = client.get("/_test/nonce", headers={"X-CSP-Nonce": "abc123"})
    assert r.status_code == 200
    assert r.text == "nonce:abc123"


def test_csp_nonce_generated_when_header_absent(
    _migrated: Settings, session_cookie: tuple[str, str]
) -> None:
    """Dev / test with no proxy: middleware mints a non-empty URL-safe nonce."""
    client = _app_with_echo_route(_migrated, session_cookie)
    with client:
        r1 = client.get("/_test/nonce")
        r2 = client.get("/_test/nonce")
    assert r1.status_code == 200
    assert r2.status_code == 200
    nonce1 = r1.text.removeprefix("nonce:")
    nonce2 = r2.text.removeprefix("nonce:")
    # Non-empty, URL-safe, and different per request.
    assert nonce1
    assert nonce2
    assert nonce1 != nonce2
    assert all(c.isalnum() or c in "-_" for c in nonce1)


def test_middleware_does_not_overwrite_pre_set_headers(
    _migrated: Settings, session_cookie: tuple[str, str]
) -> None:
    """If a downstream layer (Caddy mock) already sets a header, keep it.

    Simulated by registering a route that stamps a custom HSTS value; the
    middleware's ``if name not in response.headers`` guard must preserve it.
    """
    app = create_app(settings=_migrated)

    @app.get("/_test/pre-set", response_class=PlainTextResponse)
    def _pre_set() -> PlainTextResponse:
        resp = PlainTextResponse("ok")
        resp.headers["Strict-Transport-Security"] = "max-age=1"
        return resp

    with TestClient(app) as c:
        c.cookies.set(*session_cookie)
        r = c.get("/_test/pre-set")
    assert r.status_code == 200
    assert r.headers["Strict-Transport-Security"] == "max-age=1"
    # Other defaults should still be filled in.
    assert r.headers["X-Frame-Options"] == "DENY"
