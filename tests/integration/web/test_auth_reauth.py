"""T-D53b — step-up re-auth + session token rotation (ADR-0076 §2, §4).

Staleness is driven through ``app.state.reauth_clock`` (no sleeps): moving the
clock past ``session_reauth_window_minutes`` makes a fresh login stale.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories import sessions as sessions_repo, webauthn as webauthn_repo
from budget_planner.services import auth as auth_service, reauth as reauth_service
from budget_planner.web.auth_cookies import SESSION_COOKIE_NAME
from tests.auth_support import TEST_PASSWORD, seed_login_user

pytestmark = pytest.mark.integration

WINDOW_MINUTES = 10
WRONG_PASSWORD = "not-the-password"  # noqa: S105  # pragma: allowlist secret
NEW_PASSWORD = "a-brand-new-passphrase"  # noqa: S105  # pragma: allowlist secret
JSON_HEADERS = {"Accept": "application/json"}
HX_HEADERS = {"HX-Request": "true", "HX-Current-URL": "https://testserver/settings/security"}
PAGE_HEADERS = {"Referer": "https://testserver/settings/security"}
STALE_URL = "/auth/reauth?next=%2Fsettings%2Fsecurity"


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'web.sqlite').as_posix()}",
        session_reauth_window_minutes=WINDOW_MINUTES,
        rate_limit_reauth_per_minute=3,
        rate_limit_reauth_per_hour=50,
    )


class _Clock:
    def __init__(self) -> None:
        self.now = datetime.now(UTC)

    def __call__(self) -> datetime:
        return self.now


def _go_stale(client: TestClient) -> _Clock:
    clock = _Clock()
    clock.now += timedelta(minutes=WINDOW_MINUTES + 1)
    client.app.state.reauth_clock = clock  # type: ignore[attr-defined]
    return clock


def _token(client: TestClient, name: str) -> str | None:
    """Latest value of cookie ``name`` (server-set cookies shadow the fixture's)."""
    cookies = [c for c in client.cookies.jar if c.name == name]
    server_set = [c for c in cookies if c.domain != ""]
    chosen = server_set or cookies
    return chosen[-1].value if chosen else None


def _rows(conn: sqlite3.Connection, event: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT new_json, session_id FROM audit_log WHERE entity_type = 'auth_event'"
    ).fetchall()
    out = [{**json.loads(r["new_json"]), "session": r["session_id"]} for r in rows]
    return [r for r in out if r.get("event") == event]


@pytest.fixture
def db(settings: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(settings)
    yield conn
    conn.close()


# ---------------------------------------------------------------------------
# Stale vs fresh, per guarded route and response shape
# ---------------------------------------------------------------------------

_GUARDED: list[tuple[str, dict[str, Any]]] = [
    ("/auth/register/begin", {}),
    ("/auth/register/finish", {"json": {"label": "x", "credential": {}}}),
    ("/auth/passkeys/1/revoke", {}),
    ("/auth/sessions/{other}/revoke", {}),
]


def _other_session_handle(settings: Settings) -> str:
    conn = get_connection(settings)
    try:
        return sessions_repo.create_session(conn, 1, ip=None, user_agent="other").session.handle
    finally:
        conn.close()


@pytest.mark.parametrize(("path", "kwargs"), _GUARDED)
def test_stale_html_redirects_to_reauth(
    client: TestClient, settings: Settings, path: str, kwargs: dict[str, Any]
) -> None:
    path = path.replace("{other}", _other_session_handle(settings))
    _go_stale(client)
    r = client.post(path, headers=PAGE_HEADERS, follow_redirects=False, **kwargs)
    assert r.status_code == 303
    assert r.headers["location"] == STALE_URL


@pytest.mark.parametrize(("path", "kwargs"), _GUARDED)
def test_stale_htmx_gets_403_with_hx_redirect(
    client: TestClient, settings: Settings, path: str, kwargs: dict[str, Any]
) -> None:
    path = path.replace("{other}", _other_session_handle(settings))
    _go_stale(client)
    r = client.post(path, headers=HX_HEADERS, **kwargs)
    assert r.status_code == 403
    assert r.json() == {"error": "reauth_required"}
    assert r.headers["hx-redirect"] == STALE_URL


@pytest.mark.parametrize(("path", "kwargs"), _GUARDED)
def test_stale_json_gets_403_with_redirect(
    client: TestClient, settings: Settings, path: str, kwargs: dict[str, Any]
) -> None:
    path = path.replace("{other}", _other_session_handle(settings))
    _go_stale(client)
    r = client.post(path, headers={**JSON_HEADERS, **PAGE_HEADERS}, **kwargs)
    assert r.status_code == 403
    assert r.json() == {"error": "reauth_required", "redirect": STALE_URL}


def test_fresh_login_passes_the_guard(client: TestClient) -> None:
    assert client.post("/auth/register/begin").status_code == 200


def test_just_inside_the_window_still_passes(client: TestClient) -> None:
    clock = _Clock()
    clock.now += timedelta(minutes=WINDOW_MINUTES - 1)
    client.app.state.reauth_clock = clock  # type: ignore[attr-defined]
    assert client.post("/auth/register/begin").status_code == 200


def test_revoking_own_session_needs_no_reauth(client: TestClient, db: sqlite3.Connection) -> None:
    _go_stale(client)
    handle = sessions_repo.list_active_sessions(db, 1)[0].handle
    r = client.post(f"/auth/sessions/{handle}/revoke", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/auth/login")


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/settings/users"),
        ("post", "/settings/users/1"),
        ("post", "/settings/users/1/reset-password"),
        ("post", "/settings/users/1/delete"),
    ],
)
def test_admin_posts_are_guarded(admin_client: TestClient, method: str, path: str) -> None:
    _go_stale(admin_client)
    r = getattr(admin_client, method)(
        path, headers={"Referer": "https://testserver/settings/users"}, follow_redirects=False
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/auth/reauth?next=%2Fsettings%2Fusers"


def test_admin_reads_are_not_guarded(admin_client: TestClient) -> None:
    _go_stale(admin_client)
    assert admin_client.get("/settings/users").status_code == 200


def test_guard_ignores_foreign_referer(client: TestClient) -> None:
    _go_stale(client)
    r = client.post(
        "/auth/register/begin",
        headers={"Referer": "https://evil.example/x", "Accept": "application/json"},
    )
    assert r.json()["redirect"] == STALE_URL


# ---------------------------------------------------------------------------
# Re-auth page + password flow
# ---------------------------------------------------------------------------


def test_reauth_page_renders_without_passkey_button_when_none(client: TestClient) -> None:
    r = client.get("/auth/reauth?next=/settings/users")
    assert r.status_code == 200
    assert 'name="password"' in r.text
    assert "data-passkey-reauth" not in r.text
    assert 'value="/settings/users"' in r.text


def test_reauth_page_requires_session(anon_client: TestClient) -> None:
    r = anon_client.get("/auth/reauth", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/auth/login")


@pytest.mark.parametrize("bad_next", ["https://evil.example/", "//evil.example", "/auth/reauth"])
def test_unsafe_next_falls_back_to_landing(client: TestClient, bad_next: str) -> None:
    r = client.post(
        "/auth/reauth", data={"password": TEST_PASSWORD, "next": bad_next}, follow_redirects=False
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/today"


def test_password_reauth_rotates_cookie_and_lands_on_next(
    client: TestClient, db: sqlite3.Connection, session_cookie: tuple[str, str]
) -> None:
    name, old_token = session_cookie
    created_at = sessions_repo.get_session(db, old_token).created_at  # type: ignore[union-attr]
    _go_stale(client)
    r = client.post(
        "/auth/reauth",
        data={"password": TEST_PASSWORD, "next": "/settings/users"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/settings/users"
    new_token = _token(client, name)
    assert new_token and new_token != old_token
    assert sessions_repo.get_session(db, old_token) is None
    rotated = sessions_repo.get_session(db, new_token)
    assert rotated is not None
    assert rotated.created_at == created_at
    # The old cookie is dead: replaying it gets a login redirect.
    client.cookies.jar.clear()
    client.cookies.set(name, old_token)
    replay = client.get("/settings/security", follow_redirects=False)
    assert replay.status_code == 302
    assert replay.headers["location"].startswith("/auth/login")


def test_reauth_refreshes_the_window(client: TestClient, db: sqlite3.Connection) -> None:
    clock = _go_stale(client)
    assert client.post("/auth/register/begin", follow_redirects=False).status_code == 303
    client.post("/auth/reauth", data={"password": TEST_PASSWORD}, follow_redirects=False)
    session = sessions_repo.list_active_sessions(db, 1)[0]
    # authenticated_at is stamped with the injected clock, so the guard passes again.
    assert session.authenticated_at >= clock.now - timedelta(seconds=1)
    assert client.post("/auth/register/begin").status_code == 200


def test_wrong_password_is_generic_401_and_audited(
    client: TestClient, db: sqlite3.Connection, session_cookie: tuple[str, str]
) -> None:
    r = client.post("/auth/reauth", data={"password": WRONG_PASSWORD, "next": "/today"})
    assert r.status_code == 401
    assert "That password didn&#39;t work." in r.text or "That password didn't work." in r.text
    assert _token(client, session_cookie[0]) == session_cookie[1]  # not rotated
    failed = _rows(db, "reauth_failed")
    assert failed[-1]["method"] == "password"
    assert failed[-1]["reason"] == "bad_password"


def test_success_is_audited_with_session_handle(
    client: TestClient, db: sqlite3.Connection, session_cookie: tuple[str, str]
) -> None:
    handle = sessions_repo.session_handle(session_cookie[1])
    client.post("/auth/reauth", data={"password": TEST_PASSWORD}, follow_redirects=False)
    ok = _rows(db, "reauth")
    assert ok[-1]["method"] == "password"
    assert ok[-1]["session"] == handle


def test_reauth_rate_limit_returns_429(client: TestClient, db: sqlite3.Connection) -> None:
    codes = [
        client.post("/auth/reauth", data={"password": WRONG_PASSWORD}).status_code for _ in range(4)
    ]
    assert codes == [401, 401, 401, 429]
    r = client.post("/auth/reauth", data={"password": TEST_PASSWORD}, follow_redirects=False)
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) >= 1
    assert "data-throttled" in r.text
    assert _rows(db, "rate_limited")[-1]["scope"] == "reauth"


def test_reauth_finish_rate_limited_as_json(client: TestClient) -> None:
    codes = [client.post("/auth/reauth/finish", json={}).status_code for _ in range(4)]
    assert codes[-1] == 429


# ---------------------------------------------------------------------------
# Passkey re-auth
# ---------------------------------------------------------------------------


def _add_credential(conn: sqlite3.Connection, user_id: int, raw_id: bytes) -> None:
    webauthn_repo.create_credential(
        conn,
        user_id=user_id,
        credential_id=raw_id,
        public_key=b"pk",
        sign_count=0,
        transports=(),
        label="t",
        request_ctx=RequestCtx(ip=None, user_id=user_id, session_id=None, user_agent=None),
    )


def test_reauth_begin_lists_only_own_credentials(
    client: TestClient, db: sqlite3.Connection
) -> None:
    seed_login_user(db, user_id=2, email="two@example.test")
    _add_credential(db, 1, b"mine-credential")
    _add_credential(db, 2, b"theirs-credential")
    r = client.post("/auth/reauth/begin")
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()["allowCredentials"]]
    assert len(ids) == 1
    assert "challenge" in r.json()
    assert b"theirs" not in json.dumps(r.json()).encode()


def test_reauth_begin_without_passkeys_is_400(client: TestClient) -> None:
    r = client.post("/auth/reauth/begin")
    assert r.status_code == 400
    assert r.json() == {"error": "no_passkeys"}


def test_reauth_page_shows_passkey_button_when_user_has_one(
    client: TestClient, db: sqlite3.Connection
) -> None:
    _add_credential(db, 1, b"mine-credential")
    assert "data-passkey-reauth" in client.get("/auth/reauth").text


def test_passkey_of_another_user_is_rejected(
    _migrated: Settings, db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_login_user(db, user_id=1)
    seed_login_user(db, user_id=2, email="two@example.test")
    _add_credential(db, 2, b"theirs-credential")
    monkeypatch.setattr(
        reauth_service,
        "parse_authentication_credential_json",
        lambda _c: SimpleNamespace(raw_id=b"theirs-credential"),
    )
    ctx = RequestCtx(ip=None, user_id=1, session_id=None, user_agent=None)
    rp = auth_service.RelyingParty(rp_id="localhost", rp_name="x", origin="http://localhost")
    ok = reauth_service.verify_passkey_reauth(db, 1, {"id": "x"}, challenge=b"c", rp=rp, ctx=ctx)
    assert ok is False
    assert _rows(db, "reauth_failed")[-1]["reason"] == "unknown_credential"


def test_reauth_finish_without_challenge_fails_and_keeps_session(
    client: TestClient, session_cookie: tuple[str, str]
) -> None:
    r = client.post("/auth/reauth/finish", json={"id": "x"})
    assert r.status_code == 401
    assert r.json() == {"error": "reauth_failed"}
    assert _token(client, session_cookie[0]) == session_cookie[1]


def test_reauth_finish_rejects_other_purpose_challenge(client: TestClient) -> None:
    """A register-purpose challenge cannot complete a re-auth."""
    client.post("/auth/register/begin")
    r = client.post("/auth/reauth/finish", json={"id": "x"})
    assert r.status_code == 401


def test_passkey_finish_success_rotates_session(
    client: TestClient,
    db: sqlite3.Connection,
    session_cookie: tuple[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _add_credential(db, 1, b"mine-credential")
    client.post("/auth/reauth/begin")
    monkeypatch.setattr(reauth_service, "verify_passkey_reauth", lambda *_a, **_k: True)
    r = client.post("/auth/reauth/finish?next=/settings/security", json={"id": "x"})
    assert r.status_code == 200
    assert r.json() == {"redirect": "/settings/security"}
    new = _token(client, session_cookie[0])
    assert new and new != session_cookie[1]
    assert sessions_repo.get_session(db, session_cookie[1]) is None
    assert sessions_repo.get_session(db, new) is not None


# ---------------------------------------------------------------------------
# Password change rotates (ADR-0076 §4)
# ---------------------------------------------------------------------------


def test_password_change_rotates_token_and_keeps_created_at(
    client: TestClient, db: sqlite3.Connection, session_cookie: tuple[str, str]
) -> None:
    name, old = session_cookie
    created_at = sessions_repo.get_session(db, old).created_at  # type: ignore[union-attr]
    r = client.post(
        "/settings/password",
        data={
            "current_password": TEST_PASSWORD,
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    new = _token(client, name)
    assert new and new != old
    assert sessions_repo.get_session(db, old) is None
    rotated = sessions_repo.get_session(db, new)
    assert rotated is not None
    assert rotated.created_at == created_at
    assert (
        SESSION_COOKIE_NAME not in r.headers.get("set-cookie", "") or new in r.headers["set-cookie"]
    )
