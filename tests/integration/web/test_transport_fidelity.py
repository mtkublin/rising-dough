"""T-Q249 (Q-058): the test transport matches production.

The shared ``client`` fixture auto-attaches the CSRF header and forces
https, which hides transport-level bugs. These tests use a plain
``TestClient`` (no auto header) against real routes, and production-like
settings so the ``__Host-`` / ``Secure`` cookie path is exercised.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.web.app import create_app
from budget_planner.web.auth_cookies import SESSION_COOKIE_NAME
from budget_planner.web.middleware.csrf import (
    CSRF_COOKIE_NAME,
    CSRF_FORM_FIELD,
    CSRF_HEADER_NAME,
)
from tests.auth_support import TEST_EMAIL, TEST_PASSWORD, seed_login_user

pytestmark = pytest.mark.integration

_LOGIN = "/auth/login"
_BAD_FORM = {"email": TEST_EMAIL, "password": "wrong-password"}  # pragma: allowlist secret


@pytest.fixture
def plain_client(_migrated: Settings) -> Iterator[TestClient]:
    """Real app, plain TestClient: no priming, no auto-attached CSRF header."""
    with TestClient(create_app(settings=_migrated), base_url="https://testserver") as c:
        yield c


def test_real_route_post_without_cookie_is_rejected(plain_client: TestClient) -> None:
    r = plain_client.post(_LOGIN, data=_BAD_FORM)
    assert r.status_code == 403
    assert r.json() == {"detail": "missing_cookie"}


def test_real_route_post_with_cookie_but_no_token_is_rejected(plain_client: TestClient) -> None:
    plain_client.get(_LOGIN)
    assert CSRF_COOKIE_NAME in plain_client.cookies
    r = plain_client.post(_LOGIN, data=_BAD_FORM)
    assert r.status_code == 403
    assert r.json() == {"detail": "invalid_csrf"}


def test_real_route_post_with_mismatched_header_is_rejected(plain_client: TestClient) -> None:
    plain_client.get(_LOGIN)
    r = plain_client.post(_LOGIN, data=_BAD_FORM, headers={CSRF_HEADER_NAME: "forged"})
    assert r.status_code == 403
    assert r.json() == {"detail": "invalid_csrf"}


def test_real_route_post_with_header_token_passes_csrf(plain_client: TestClient) -> None:
    token = plain_client.get(_LOGIN).cookies[CSRF_COOKIE_NAME]
    r = plain_client.post(_LOGIN, data=_BAD_FORM, headers={CSRF_HEADER_NAME: token})
    # Past CSRF: the login handler itself answers (generic failure).
    assert r.status_code == 401


def test_real_route_post_with_form_token_passes_csrf(plain_client: TestClient) -> None:
    token = plain_client.get(_LOGIN).cookies[CSRF_COOKIE_NAME]
    r = plain_client.post(_LOGIN, data={**_BAD_FORM, CSRF_FORM_FIELD: token})
    assert r.status_code == 401


def _production_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        env="production",
        cookie_secret="x" * 32,  # pragma: allowlist secret
        webauthn_rp_id="budget.example.test",
        webauthn_origin="https://budget.example.test",
        database_url=f"sqlite:///{(tmp_path / 'prod_sim.db').as_posix()}",
        admin_email="admin@prodsim.test",
        admin_initial_password="prodsim-only",  # noqa: S106  # pragma: allowlist secret
    )


def test_production_login_sets_host_prefixed_secure_cookies(tmp_path: Path) -> None:
    cfg = _production_settings(tmp_path)
    conn = get_connection(cfg)
    try:
        apply_migrations(conn)
        seed_login_user(conn, user_id=1)
    finally:
        conn.close()
    with TestClient(create_app(settings=cfg), base_url="https://testserver") as c:
        first = c.get(_LOGIN)
        token = first.cookies[CSRF_COOKIE_NAME]
        minted = first.headers.get("set-cookie", "").lower()
        r = c.post(
            _LOGIN,
            data={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            headers={CSRF_HEADER_NAME: token},
            follow_redirects=False,
        )
    assert minted.startswith("__host-csrf=")
    assert "secure" in minted
    assert "domain" not in minted
    assert r.status_code == 303
    assert SESSION_COOKIE_NAME == "__Host-session"
    cookies = [h.lower() for h in r.headers.get_list("set-cookie")]
    session = [h for h in cookies if h.startswith("__host-session=")]
    assert len(session) == 1, cookies
    for flag in ("httponly", "secure", "samesite=lax", "path=/"):
        assert flag in session[0]
    assert "domain" not in session[0]
