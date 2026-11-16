"""T-D18a — rate limit on ``POST /settings/password`` (ADR-0072, ADR-0074 §4).

Same mechanism as the auth routes: per-user fixed-window counters, clock
injected via ``app.state.rate_limit_clock``.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.web.app import create_app
from budget_planner.web.routers.settings_password import THROTTLED_FORM_ERROR
from tests.auth_support import TEST_PASSWORD, login_cookie
from tests.integration.web.conftest import _CSRFAwareTestClient

pytestmark = pytest.mark.integration

PER_MINUTE = 2
T0 = datetime(2026, 11, 3, 12, 0, 10, tzinfo=UTC)
WRONG = "not-the-password"  # pragma: allowlist secret
HX = {"HX-Request": "true"}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'web.sqlite').as_posix()}",
        rate_limit_password_change_per_minute=PER_MINUTE,
        rate_limit_password_change_per_hour=50,
    )


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock(client: TestClient) -> _Clock:
    c = _Clock(T0)
    client.app.state.rate_limit_clock = c  # type: ignore[attr-defined]
    return c


def _post(client: TestClient, current: str = WRONG, **kw: Any) -> Any:
    return client.post(
        "/settings/password",
        data={
            "current_password": current,
            "new_password": "a-brand-new-passphrase",  # pragma: allowlist secret
            "confirm_password": "a-brand-new-passphrase",  # pragma: allowlist secret
        },
        follow_redirects=False,
        **kw,
    )


def _burn(client: TestClient) -> None:
    for _ in range(PER_MINUTE):
        assert _post(client).status_code == 422


def test_limit_fires_with_429_and_retry_after(client: TestClient, clock: _Clock) -> None:
    _burn(client)
    r = _post(client)
    assert r.status_code == 429
    assert r.headers["retry-after"] == "50"
    assert THROTTLED_FORM_ERROR in r.text
    assert "data-throttled" in r.text


def test_throttled_correct_password_is_not_applied(
    client: TestClient, clock: _Clock, conn: sqlite3.Connection
) -> None:
    _burn(client)
    before = conn.execute("SELECT password_hash FROM users WHERE id = 1").fetchone()[0]
    r = _post(client, TEST_PASSWORD)
    assert r.status_code == 429
    after = conn.execute("SELECT password_hash FROM users WHERE id = 1").fetchone()[0]
    assert before == after
    failed = conn.execute(
        "SELECT COUNT(*) FROM audit_log WHERE new_json LIKE '%password_change_failed%'"
    ).fetchone()[0]
    assert failed == PER_MINUTE  # no bcrypt verify ran for the throttled attempt


def test_htmx_rerenders_form_fragment(client: TestClient, clock: _Clock) -> None:
    _burn(client)
    r = _post(client, headers=HX)
    assert r.status_code == 429
    assert r.text.lstrip().startswith("<form")
    assert THROTTLED_FORM_ERROR in r.text


def test_json_gets_rate_limited_error(client: TestClient, clock: _Clock) -> None:
    _burn(client)
    r = _post(client, headers={"Accept": "application/json"})
    assert r.status_code == 429
    assert r.json() == {"error": "rate_limited"}
    assert r.headers["retry-after"] == "50"


def test_throttled_attempt_writes_audit_row(
    client: TestClient, clock: _Clock, conn: sqlite3.Connection
) -> None:
    _burn(client)
    _post(client)
    rows = conn.execute(
        "SELECT entity_id, new_json FROM audit_log WHERE entity_type = 'auth_event'"
    ).fetchall()
    throttled = [(r[0], json.loads(r[1])) for r in rows if "rate_limited" in r[1]]
    assert throttled == [(1, {"event": "rate_limited", "scope": "password_change"})]


def test_window_reset_allows_again(client: TestClient, clock: _Clock) -> None:
    _burn(client)
    assert _post(client).status_code == 429
    clock.now = T0 + timedelta(seconds=50)
    assert _post(client).status_code == 422


def test_other_user_is_unaffected(client: TestClient, clock: _Clock, settings: Settings) -> None:
    _burn(client)
    assert _post(client).status_code == 429
    name, value = login_cookie(settings, user_id=2, email="second@example.test")
    client.cookies.delete(name)
    client.cookies.set(name, value)
    assert _post(client).status_code == 422


def test_kill_switch_disables_limit(tmp_path: Path, session_cookie: tuple[str, str]) -> None:
    off = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'web.sqlite').as_posix()}",
        rate_limit_enabled=False,
        rate_limit_password_change_per_minute=1,
        rate_limit_password_change_per_hour=1,
    )
    with _CSRFAwareTestClient(create_app(settings=off)) as c:
        c.cookies.set(*session_cookie)
        codes = [_post(c).status_code for _ in range(4)]
    assert codes == [422] * 4


def test_security_tab_hosts_change_password_form(client: TestClient) -> None:
    r = client.get("/settings/security")
    assert r.status_code == 200
    assert 'action="/settings/password"' in r.text
    assert "Change password" in r.text
