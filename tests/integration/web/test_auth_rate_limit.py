"""T-D09 — rate limits on the auth routes (ADR-0072).

Limits are tightened through the module-level ``settings`` override; the
clock is injected via ``app.state.rate_limit_clock`` so window resets are
deterministic.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.web.auth_cookies import SESSION_COOKIE_NAME
from budget_planner.web.routers.auth import GENERIC_LOGIN_ERROR, RATE_LIMITED_LOGIN_ERROR
from tests.auth_support import TEST_EMAIL, TEST_PASSWORD, seed_login_user

pytestmark = pytest.mark.integration

LOGIN_PER_MINUTE = 2
T0 = datetime(2026, 11, 3, 12, 0, 10, tzinfo=UTC)
_CREDENTIAL: dict[str, Any] = {"id": "abc", "rawId": "abc", "type": "public-key", "response": {}}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'web.sqlite').as_posix()}",
        rate_limit_login_per_minute=LOGIN_PER_MINUTE,
        rate_limit_login_per_hour=4,
        rate_limit_login_ip_per_hour=5,
        rate_limit_passkey_login_per_minute=2,
        rate_limit_passkey_login_per_hour=50,
        rate_limit_register_per_minute=1,
        rate_limit_register_per_hour=50,
    )


class _Clock:
    """Settable test clock (tests advance it explicitly)."""

    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now


def _install_clock(client: TestClient) -> _Clock:
    clock = _Clock(T0)
    client.app.state.rate_limit_clock = clock  # type: ignore[attr-defined]
    return clock


@pytest.fixture
def anon(anon_client: TestClient) -> tuple[TestClient, _Clock]:
    return anon_client, _install_clock(anon_client)


@pytest.fixture
def login_user(conn: sqlite3.Connection) -> int:
    return seed_login_user(conn)


def _login(client: TestClient, email: str, password: str, **kw: Any) -> Any:
    return client.post(
        "/auth/login",
        data={"email": email, "password": password, "next": "/"},
        follow_redirects=False,
        **kw,
    )


def _burn(fn: Callable[[], Any], times: int) -> list[int]:
    return [fn().status_code for _ in range(times)]


# ---------------------------------------------------------------------------
# Password login
# ---------------------------------------------------------------------------


def test_password_login_throttles_with_429_and_retry_after(
    anon: tuple[TestClient, _Clock], login_user: int
) -> None:
    client, _ = anon
    codes = _burn(lambda: _login(client, TEST_EMAIL, "wrong"), LOGIN_PER_MINUTE)
    assert codes == [401, 401]
    r = _login(client, TEST_EMAIL, "wrong")
    assert r.status_code == 429
    assert r.headers["retry-after"] == "50"
    assert RATE_LIMITED_LOGIN_ERROR in r.text
    assert GENERIC_LOGIN_ERROR not in r.text
    assert 'aria-invalid="true"' not in r.text
    assert "data-throttled" in r.text


def test_throttled_login_does_not_sign_in_even_with_correct_password(
    anon: tuple[TestClient, _Clock], login_user: int
) -> None:
    client, _ = anon
    _burn(lambda: _login(client, TEST_EMAIL, "wrong"), LOGIN_PER_MINUTE)
    r = _login(client, TEST_EMAIL, TEST_PASSWORD)
    assert r.status_code == 429
    assert not [h for h in r.headers.get_list("set-cookie") if h.startswith(SESSION_COOKIE_NAME)]


def test_successful_login_does_not_reset_the_counter(
    anon: tuple[TestClient, _Clock], login_user: int
) -> None:
    client, _ = anon
    assert _login(client, TEST_EMAIL, TEST_PASSWORD).status_code == 303
    assert _login(client, TEST_EMAIL, TEST_PASSWORD).status_code == 303
    assert _login(client, TEST_EMAIL, TEST_PASSWORD).status_code == 429


def test_window_reset_allows_login_again(anon: tuple[TestClient, _Clock], login_user: int) -> None:
    client, clock = anon
    _burn(lambda: _login(client, TEST_EMAIL, "wrong"), LOGIN_PER_MINUTE + 1)
    clock.now = T0 + timedelta(seconds=50)
    assert _login(client, TEST_EMAIL, TEST_PASSWORD).status_code == 303


def test_hour_window_outlasts_minute_window(
    anon: tuple[TestClient, _Clock], login_user: int
) -> None:
    client, clock = anon
    for minute in range(2):  # 2 + 2 = 4 = hourly limit
        clock.now = T0 + timedelta(minutes=minute)
        _burn(lambda: _login(client, TEST_EMAIL, "wrong"), LOGIN_PER_MINUTE)
    clock.now = T0 + timedelta(minutes=2)
    r = _login(client, TEST_EMAIL, "wrong")
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) == 3600 - 10 - 120


def test_email_is_case_insensitive_for_the_counter(
    anon: tuple[TestClient, _Clock], login_user: int
) -> None:
    client, _ = anon
    _burn(lambda: _login(client, TEST_EMAIL.upper(), "wrong"), LOGIN_PER_MINUTE)
    assert _login(client, f"  {TEST_EMAIL} ", "wrong").status_code == 429


def test_other_email_is_not_affected(anon: tuple[TestClient, _Clock], login_user: int) -> None:
    client, _ = anon
    _burn(lambda: _login(client, "someone@example.test", "wrong"), LOGIN_PER_MINUTE + 1)
    assert _login(client, TEST_EMAIL, TEST_PASSWORD).status_code == 303


def test_per_ip_backstop_catches_email_spraying(
    anon: tuple[TestClient, _Clock], login_user: int
) -> None:
    client, _ = anon
    codes = [_login(client, f"u{i}@example.test", "wrong").status_code for i in range(6)]
    assert codes == [401] * 5 + [429]


def test_htmx_and_json_callers_get_json_429(
    anon: tuple[TestClient, _Clock], login_user: int
) -> None:
    client, _ = anon
    _burn(lambda: _login(client, TEST_EMAIL, "wrong"), LOGIN_PER_MINUTE)
    hx = _login(client, TEST_EMAIL, "wrong", headers={"HX-Request": "true"})
    js = _login(client, TEST_EMAIL, "wrong", headers={"Accept": "application/json"})
    for r in (hx, js):
        assert r.status_code == 429
        assert r.json() == {"error": "rate_limited"}
        assert int(r.headers["retry-after"]) > 0


def test_throttled_login_writes_audit_row(
    anon: tuple[TestClient, _Clock], login_user: int, conn: sqlite3.Connection
) -> None:
    client, _ = anon
    _burn(lambda: _login(client, TEST_EMAIL, "wrong"), LOGIN_PER_MINUTE + 1)
    rows = conn.execute(
        "SELECT new_json, ip FROM audit_log WHERE entity_type = 'auth_event'"
    ).fetchall()
    events = [json.loads(r[0]) for r in rows]
    throttled = [e for e in events if e["event"] == "rate_limited"]
    assert throttled == [{"event": "rate_limited", "scope": "login", "email": TEST_EMAIL}]
    assert all(r[1] == "testclient" for r in rows)


def test_rate_limit_disabled_never_throttles(tmp_path: Path, login_user: int) -> None:
    from budget_planner.web.app import create_app  # noqa: PLC0415
    from tests.integration.web.conftest import _CSRFAwareTestClient  # noqa: PLC0415

    del login_user
    off = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'web.sqlite').as_posix()}",
        rate_limit_enabled=False,
        rate_limit_login_per_minute=1,
    )
    with _CSRFAwareTestClient(create_app(settings=off)) as c:
        assert set(_burn(lambda: _login(c, TEST_EMAIL, "wrong"), 4)) == {401}


# ---------------------------------------------------------------------------
# Passkey login finish (per IP)
# ---------------------------------------------------------------------------


def test_passkey_login_finish_throttles_per_ip(anon: tuple[TestClient, _Clock]) -> None:
    client, clock = anon

    def post() -> Any:
        return client.post("/auth/login/finish", json=_CREDENTIAL)

    assert _burn(post, 2) == [401, 401]
    r = post()
    assert r.status_code == 429
    assert r.json() == {"error": "rate_limited"}
    assert r.headers["retry-after"] == "50"
    clock.now = T0 + timedelta(minutes=1)
    assert post().status_code == 401


def test_passkey_login_counter_is_separate_from_password_login(
    anon: tuple[TestClient, _Clock], login_user: int
) -> None:
    client, _ = anon
    _burn(lambda: client.post("/auth/login/finish", json=_CREDENTIAL), 3)
    assert _login(client, TEST_EMAIL, TEST_PASSWORD).status_code == 303


# ---------------------------------------------------------------------------
# Passkey register finish (per user)
# ---------------------------------------------------------------------------


def test_register_finish_throttles_per_user(client: TestClient, conn: sqlite3.Connection) -> None:
    _install_clock(client)
    body = {"label": "x", "credential": _CREDENTIAL}
    first = client.post("/auth/register/finish", json=body)
    assert first.status_code == 400  # no challenge cookie → challenge_expired
    r = client.post("/auth/register/finish", json=body)
    assert r.status_code == 429
    assert r.json() == {"error": "rate_limited"}
    assert r.headers["retry-after"] == "50"
    row = conn.execute(
        "SELECT entity_id, user_id, new_json FROM audit_log "
        "WHERE entity_type = 'auth_event' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert (row[0], row[1]) == (1, 1)
    assert json.loads(row[2]) == {"event": "rate_limited", "scope": "passkey_register"}


def test_register_finish_counter_is_per_user(
    client: TestClient, conn: sqlite3.Connection, settings: Settings
) -> None:
    from tests.auth_support import login_cookie  # noqa: PLC0415

    _install_clock(client)
    body = {"label": "x", "credential": _CREDENTIAL}
    client.post("/auth/register/finish", json=body)
    assert client.post("/auth/register/finish", json=body).status_code == 429

    name, value = login_cookie(settings, user_id=2, email="second@example.test")
    client.cookies.delete(name)  # drop every copy (server refreshes it with a domain)
    client.cookies.set(name, value)
    assert client.post("/auth/register/finish", json=body).status_code == 400
