"""T-D02b — ``AuthRequiredMiddleware`` gating, hydration, and deps (ADR-0070)."""

from __future__ import annotations

import sqlite3
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.repositories import sessions as sessions_repo
from budget_planner.repositories.sessions import session_handle
from budget_planner.services import auth as auth_service
from budget_planner.web.app import create_app
from budget_planner.web.auth_cookies import SESSION_COOKIE_NAME, SESSION_DEV_COOKIE_NAME
from budget_planner.web.deps import current_user_id, get_request_ctx
from budget_planner.web.middleware.auth import CurrentUser, is_exempt
from tests.auth_support import issue_session, login_cookie

pytestmark = pytest.mark.integration


def _echo_app(settings: Settings) -> TestClient:
    app = create_app(settings=settings)

    @app.get("/_test/whoami")
    def _whoami(request: Request) -> JSONResponse:
        user = request.state.user
        ctx = get_request_ctx(request)
        return JSONResponse(
            {
                "id": user.id,
                "email": user.email,
                "is_admin": user.is_admin,
                "must_change_password": user.must_change_password,
                "ctx_session": ctx.session_id,
                "ctx_user": ctx.user_id,
                "has_hash": hasattr(user, "password_hash"),
            }
        )

    return TestClient(app, base_url="https://testserver")


# ---------------------------------------------------------------------------
# Unauthenticated responses
# ---------------------------------------------------------------------------


def test_html_request_redirects_to_login_with_next(anon_client: TestClient) -> None:
    r = anon_client.get("/ledger?tab=planned", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/auth/login?next=%2Fledger%3Ftab%3Dplanned"
    # Outer middlewares still decorate the redirect (ADR-0070 §6).
    assert r.headers.get("X-Request-Id")
    assert r.headers.get("X-Frame-Options") == "DENY"


def test_root_redirects_to_bare_login(anon_client: TestClient) -> None:
    r = anon_client.get("/", follow_redirects=False)
    assert r.headers["location"] == "/auth/login"


def test_htmx_request_gets_401_with_hx_redirect(anon_client: TestClient) -> None:
    r = anon_client.get(
        "/accounts",
        headers={"HX-Request": "true", "HX-Current-URL": "https://testserver/plan?tab=year"},
        follow_redirects=False,
    )
    assert r.status_code == 401
    assert r.json() == {"error": "unauthorized"}
    assert r.headers["HX-Redirect"] == "/auth/login?next=%2Fplan%3Ftab%3Dyear"


def test_htmx_foreign_current_url_is_ignored(anon_client: TestClient) -> None:
    r = anon_client.get(
        "/accounts",
        headers={"HX-Request": "true", "HX-Current-URL": "https://evil.example/steal"},
    )
    assert r.status_code == 401
    assert r.headers["HX-Redirect"] == "/auth/login"


def test_htmx_without_current_url(anon_client: TestClient) -> None:
    r = anon_client.get("/accounts", headers={"HX-Request": "true"})
    assert r.headers["HX-Redirect"] == "/auth/login"


def test_json_client_gets_401(anon_client: TestClient) -> None:
    r = anon_client.get("/accounts", headers={"Accept": "application/json"})
    assert r.status_code == 401
    assert r.json() == {"error": "unauthorized"}


def test_unauthenticated_post_is_401_or_redirect_not_csrf(anon_client: TestClient) -> None:
    r = anon_client.post("/transactions", data={}, follow_redirects=False)
    assert r.status_code == 302


@pytest.mark.parametrize("path", ["/health", "/ready", "/auth/login"])
def test_exempt_paths_reachable_anonymously(anon_client: TestClient, path: str) -> None:
    assert anon_client.get(path, follow_redirects=False).status_code == 200


def test_static_is_exempt(anon_client: TestClient) -> None:
    r = anon_client.get("/static/js/passkeys.js")
    assert r.status_code == 200


@pytest.mark.parametrize(
    ("path", "exempt"),
    [
        ("/auth/login", True),
        ("/auth/login/begin", True),
        ("/auth/login/finish", True),
        ("/auth/logout", False),
        ("/auth/register", False),
        ("/auth/sessions", False),
        ("/static/app.css", True),
        ("/today", False),
        ("/healthz", True),
    ],
)
def test_is_exempt(path: str, exempt: bool) -> None:
    assert is_exempt(path) is exempt


# ---------------------------------------------------------------------------
# Stale sessions
# ---------------------------------------------------------------------------


def _assert_rejected_and_cleared(client: TestClient) -> None:
    r = client.get("/accounts", follow_redirects=False)
    assert r.status_code == 302
    cleared = [h for h in r.headers.get_list("set-cookie") if h.startswith(SESSION_COOKIE_NAME)]
    assert cleared
    assert "max-age=0" in cleared[0].lower()


def test_revoked_session_is_rejected(
    client: TestClient, session_cookie: tuple[str, str], conn: sqlite3.Connection
) -> None:
    sessions_repo.revoke_session(conn, session_cookie[1])
    _assert_rejected_and_cleared(client)


def test_expired_session_is_rejected(
    client: TestClient, session_cookie: tuple[str, str], conn: sqlite3.Connection
) -> None:
    past = (datetime.now(UTC) - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    conn.execute("UPDATE sessions SET expires_at = ? WHERE id = ?", (past, session_cookie[1]))
    conn.commit()
    _assert_rejected_and_cleared(client)


def test_deleted_user_session_is_rejected(client: TestClient, conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE users SET deleted_at = '2026-01-01T00:00:00.000Z' WHERE id = 1")
    conn.commit()
    _assert_rejected_and_cleared(client)


def test_unknown_cookie_on_exempt_path_is_cleared(anon_client: TestClient) -> None:
    anon_client.cookies.set(SESSION_COOKIE_NAME, "garbage")
    r = anon_client.get("/auth/login")
    assert r.status_code == 200
    assert any(
        h.startswith(SESSION_COOKIE_NAME) and "max-age=0" in h.lower()
        for h in r.headers.get_list("set-cookie")
    )


def test_db_error_fails_closed(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_a: Any, **_k: Any) -> None:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(auth_service, "load_session_user", _boom)
    r = client.get("/accounts", follow_redirects=False)
    assert r.status_code == 302


# ---------------------------------------------------------------------------
# Hydration
# ---------------------------------------------------------------------------


def test_authenticated_request_slides_cookie_and_session(
    client: TestClient, session_cookie: tuple[str, str], conn: sqlite3.Connection
) -> None:
    before = sessions_repo.get_session(conn, session_cookie[1])
    assert before is not None
    r = client.get("/accounts")
    assert r.status_code == 200
    refreshed = [h for h in r.headers.get_list("set-cookie") if h.startswith(SESSION_COOKIE_NAME)]
    assert len(refreshed) == 1
    assert f"max-age={14 * 86_400}" in refreshed[0].lower()
    after = sessions_repo.get_session(conn, session_cookie[1])
    assert after is not None
    assert after.expires_at >= before.expires_at


def test_request_state_user_shape(_migrated: Settings, conn: sqlite3.Connection) -> None:
    cookie = login_cookie(_migrated)
    # must_change_password stays 0 here: with the flag set, T-D18's
    # MustChangePasswordMiddleware gates /_test/whoami (hydration of the
    # True value is proven by tests/integration/web/test_settings_password.py).
    conn.execute("UPDATE users SET is_admin = 1 WHERE id = 1")
    conn.commit()
    with _echo_app(_migrated) as c:
        c.cookies.set(*cookie)
        body = c.get("/_test/whoami").json()
    assert body["id"] == 1
    assert body["email"] == "owner@example.test"
    assert body["is_admin"] is True
    assert body["must_change_password"] is False
    assert body["has_hash"] is False
    assert body["ctx_user"] == 1
    assert body["ctx_session"] == session_handle(cookie[1])


def test_dev_env_uses_unprefixed_session_cookie(tmp_path: Path) -> None:
    db_url = f"sqlite:///{(tmp_path / 'dev.sqlite').as_posix()}"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        cfg = Settings(_env_file=None, env="dev", database_url=db_url)
    conn = get_connection(cfg)
    try:
        apply_migrations(conn)
        session_id = issue_session(conn)
    finally:
        conn.close()
    with TestClient(create_app(settings=cfg)) as c:
        c.cookies.set(SESSION_DEV_COOKIE_NAME, session_id)
        r = c.get("/accounts", follow_redirects=False)
    assert r.status_code == 200
    refreshed = [
        h for h in r.headers.get_list("set-cookie") if h.startswith(f"{SESSION_DEV_COOKIE_NAME}=")
    ]
    assert refreshed
    assert "secure" not in refreshed[0].lower()


# ---------------------------------------------------------------------------
# deps
# ---------------------------------------------------------------------------


def _fake_request(**state: Any) -> Request:
    return SimpleNamespace(  # type: ignore[return-value]
        state=SimpleNamespace(**state),
        client=None,
        headers={},
    )


def test_current_user_id_raises_401_without_user() -> None:
    with pytest.raises(HTTPException) as exc:
        current_user_id(_fake_request())
    assert exc.value.status_code == 401


def test_current_user_id_reads_state_user() -> None:
    user = CurrentUser(id=7, email=None, name="x", is_admin=False, must_change_password=False)
    assert current_user_id(_fake_request(user=user)) == 7


def test_get_request_ctx_without_user() -> None:
    ctx = get_request_ctx(_fake_request())
    assert ctx.user_id is None
    assert ctx.session_id is None
    assert ctx.ip is None
