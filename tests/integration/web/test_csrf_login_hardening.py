"""T-Q312 — login-CSRF hardening (ADR-0065 amendment 2026-11-23).

Origin check, pre-session token lifetime and per-browser binding.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import timedelta

import pytest
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.adapters.entropy import SecretsTokenSource
from budget_planner.config import Settings
from budget_planner.web.app import create_app
from budget_planner.web.csrf_token import (
    PRE_SESSION_TOKEN_MAX_AGE,
    TokenStatus,
    browser_binding,
    check_token,
    mint_token,
    session_binding,
)
from budget_planner.web.middleware.csrf import (
    BROWSER_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
)
from budget_planner.web.middleware.csrf_origin import origin_matches
from tests.auth_support import TEST_EMAIL, TEST_PASSWORD, issue_session, seed_login_user
from tests.conftest import NO_ORIGIN_HEADER
from tests.ui_map import auth
from tests.ui_map._html import exists, text_of

pytestmark = pytest.mark.integration

ORIGIN = "http://localhost:8000"  # Settings.webauthn_origin default
SESSION_COOKIE = "__Host-session"
SECRET = "s" * 32  # pragma: allowlist secret
EXPIRED_NOTICE = "This page expired, please try again."
PROBE = "/auth/login"  # anonymous unsafe route: a passing request answers 401 (no such user)
ECHO = "/_test/echo"  # signed-in probe


def _build(settings: Settings) -> TestClient:
    app = create_app(settings=settings)

    @app.post(ECHO, response_class=PlainTextResponse)
    def _echo() -> PlainTextResponse:
        return PlainTextResponse("ok")

    return TestClient(app, base_url="https://testserver")


@pytest.fixture
def app_client(_migrated: Settings) -> TestClient:
    return _build(_migrated)


def _primed(c: TestClient) -> str:
    assert c.get("/auth/login").status_code == 200
    return c.cookies[CSRF_COOKIE_NAME]


def _form_token(html: str) -> str:
    match = re.search(r'name="_csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


# --- Origin check ---------------------------------------------------------------------------


@pytest.mark.parametrize("site", ["cross-site", "same-site", "none"])
def test_non_same_origin_fetch_site_is_rejected(app_client: TestClient, site: str) -> None:
    token = _primed(app_client)
    r = app_client.post(PROBE, headers={CSRF_HEADER_NAME: token, "Sec-Fetch-Site": site})
    assert (r.status_code, r.json()) == (403, {"detail": "cross_origin"})


def test_fetch_site_wins_over_a_matching_origin(app_client: TestClient) -> None:
    token = _primed(app_client)
    r = app_client.post(
        PROBE,
        headers={CSRF_HEADER_NAME: token, "Sec-Fetch-Site": "cross-site", "Origin": ORIGIN},
    )
    assert (r.status_code, r.json()) == (403, {"detail": "cross_origin"})


def test_mismatched_origin_is_rejected(app_client: TestClient) -> None:
    token = _primed(app_client)
    r = app_client.post(PROBE, headers={CSRF_HEADER_NAME: token, "Origin": "https://evil.example"})
    assert (r.status_code, r.json()) == (403, {"detail": "cross_origin"})


def test_missing_origin_and_fetch_site_is_rejected(app_client: TestClient) -> None:
    token = _primed(app_client)
    r = app_client.post(PROBE, headers={CSRF_HEADER_NAME: token, NO_ORIGIN_HEADER: "1"})
    assert (r.status_code, r.json()) == (403, {"detail": "cross_origin"})


@pytest.mark.parametrize(
    "headers", [{"Sec-Fetch-Site": "same-origin"}, {"Origin": ORIGIN}, {"Origin": ORIGIN + "/"}]
)
def test_same_origin_is_accepted(app_client: TestClient, headers: dict[str, str]) -> None:
    token = _primed(app_client)
    r = app_client.post(PROBE, headers={CSRF_HEADER_NAME: token, NO_ORIGIN_HEADER: "1", **headers})
    assert r.status_code == 401
    assert exists(r.text, auth.login_error)  # reached the handler: wrong credentials


def test_health_routes_are_exempt_from_origin_and_token(app_client: TestClient) -> None:
    r = app_client.post("/health", headers={NO_ORIGIN_HEADER: "1"})
    assert r.status_code != 403
    assert r.json() != {"detail": "cross_origin"}


def test_safe_methods_are_not_origin_checked(app_client: TestClient) -> None:
    r = app_client.get("/auth/login", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 200


def test_origin_matching_rules(_migrated: Settings) -> None:
    dev = _migrated.model_copy(update={"env": "dev"})
    assert origin_matches("http://localhost:8000", _migrated)
    assert not origin_matches("http://127.0.0.1:8000", _migrated)
    assert not origin_matches("http://localhost:8000.evil.example", _migrated)
    assert not origin_matches("null", _migrated)
    assert origin_matches("http://127.0.0.1:8123", dev)
    assert not origin_matches("https://127.0.0.1:8000", dev)
    assert not origin_matches("http://evil.example", dev)


# --- Pre-session token lifetime -------------------------------------------------------------


def test_token_status_by_age() -> None:
    now = clock.utc_now()
    pre = browser_binding("b1")
    token = mint_token(SECRET, pre, SecretsTokenSource(), now)
    assert check_token(SECRET, token, pre, now + PRE_SESSION_TOKEN_MAX_AGE) is TokenStatus.VALID
    just_late = now + PRE_SESSION_TOKEN_MAX_AGE + timedelta(seconds=1)
    assert check_token(SECRET, token, pre, just_late) is TokenStatus.EXPIRED
    assert check_token(SECRET, token, pre, now - timedelta(hours=1)) is TokenStatus.INVALID
    sess = session_binding("s1")
    long_lived = mint_token(SECRET, sess, SecretsTokenSource(), now)
    assert check_token(SECRET, long_lived, sess, now + timedelta(days=30)) is TokenStatus.VALID


def test_expired_login_form_rerenders_login_with_fresh_token(
    app_client: TestClient, conn: sqlite3.Connection
) -> None:
    seed_login_user(conn)
    page = app_client.get("/auth/login")
    stale = _form_token(page.text)
    with clock.frozen(clock.utc_now() + timedelta(hours=3)):
        r = app_client.post(
            "/auth/login",
            data={"email": TEST_EMAIL, "password": TEST_PASSWORD, "_csrf_token": stale},
            follow_redirects=False,
        )
        assert r.status_code == 403
        assert r.headers["content-type"].startswith("text/html")
        assert text_of(r.text, auth.login_error) == EXPIRED_NOTICE
        assert exists(r.text, auth.login_heading)
        assert SESSION_COOKIE not in app_client.cookies  # no login happened
        fresh = _form_token(r.text)
        assert fresh != stale
        assert app_client.cookies[CSRF_COOKIE_NAME] == fresh
        retry = app_client.post(
            "/auth/login",
            data={"email": TEST_EMAIL, "password": TEST_PASSWORD, "_csrf_token": fresh},
            follow_redirects=False,
        )
        assert retry.status_code == 303
        assert SESSION_COOKIE in app_client.cookies


@pytest.mark.parametrize(
    "headers", [{"HX-Request": "true"}, {"Accept": "application/json"}], ids=["htmx", "json"]
)
def test_expired_token_keeps_json_rejection_for_htmx_and_json(
    app_client: TestClient, headers: dict[str, str]
) -> None:
    token = _primed(app_client)
    with clock.frozen(clock.utc_now() + timedelta(hours=3)):
        r = app_client.post(PROBE, data={"_csrf_token": token, "email": "a@b.c"}, headers=headers)
    assert (r.status_code, r.json()) == (403, {"detail": "invalid_csrf"})


def test_expired_non_form_post_is_not_rerendered(app_client: TestClient) -> None:
    token = _primed(app_client)
    with clock.frozen(clock.utc_now() + timedelta(hours=3)):
        r = app_client.post(PROBE, json={"email": "a@b.c"}, headers={CSRF_HEADER_NAME: token})
    assert (r.status_code, r.json()) == (403, {"detail": "invalid_csrf"})


# --- Per-browser binding --------------------------------------------------------------------


def test_browser_cookie_is_httponly_lax_and_secure(app_client: TestClient) -> None:
    r = app_client.get("/auth/login")
    raw = next(
        v for v in r.headers.get_list("set-cookie") if v.startswith(f"{BROWSER_COOKIE_NAME}=")
    )
    lowered = raw.lower()
    assert "httponly" in lowered
    assert "samesite=lax" in lowered
    assert "secure" in lowered
    assert "path=/" in lowered
    assert "domain" not in lowered


def test_token_from_another_browser_is_refused(_migrated: Settings) -> None:
    attacker, victim = _build(_migrated), _build(_migrated)
    stolen = _primed(attacker)
    _primed(victim)
    victim.cookies.set(CSRF_COOKIE_NAME, stolen)  # keeps the victim's own browser id
    r = victim.post(PROBE, headers={CSRF_HEADER_NAME: stolen})
    assert (r.status_code, r.json()) == (403, {"detail": "invalid_csrf"})
    ok = attacker.post(PROBE, headers={CSRF_HEADER_NAME: stolen})
    assert ok.status_code == 401  # the owner's own token passes the CSRF layer


def test_anonymous_unsafe_request_without_browser_id_is_refused(app_client: TestClient) -> None:
    token = _primed(app_client)
    del app_client.cookies[BROWSER_COOKIE_NAME]
    r = app_client.post(PROBE, headers={CSRF_HEADER_NAME: token})
    assert (r.status_code, r.json()) == (403, {"detail": "missing_browser_id"})


def test_session_flow_is_unchanged_and_ignores_the_browser_id(
    app_client: TestClient, conn: sqlite3.Connection
) -> None:
    seed_login_user(conn)
    app_client.cookies.set(SESSION_COOKIE, issue_session(conn))
    app_client.get("/health")
    token = app_client.cookies[CSRF_COOKIE_NAME]
    ok = app_client.post(ECHO, headers={CSRF_HEADER_NAME: token})
    assert (ok.status_code, ok.text) == (200, "ok")
    app_client.cookies.clear()
    app_client.cookies.set(SESSION_COOKIE, issue_session(conn))
    app_client.cookies.set(CSRF_COOKIE_NAME, token)
    other = app_client.post(ECHO, headers={CSRF_HEADER_NAME: token})
    assert (other.status_code, other.json()) == (403, {"detail": "invalid_csrf"})
