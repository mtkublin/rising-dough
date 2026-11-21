"""``/settings/password``: forced rotation page, change, rate limit (T-UT04e, ADR-0106 section 1).

Bodies are inspected only through the UI map. bcrypt is pinned to cost 4 for
this module only (a local autouse fixture, never a session-wide one).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from bs4 import Tag
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.repositories import sessions as sessions_repo
from budget_planner.services import _passwords
from budget_planner.web.routers.settings_password import THROTTLED_FORM_ERROR
from tests.auth_support import FAST_ROUNDS, TEST_PASSWORD, issue_session, login_cookie
from tests.contract.conftest import covers
from tests.contract.web_helpers_t_ut04e import HX
from tests.ui_map import _html, settings as ui

pytest_plugins = ["tests.contract.web_support_t_ut04e"]  # client, raw_client, anon_client, db

NEW_PASSWORD = "a-brand-new-passphrase"  # noqa: S105  # pragma: allowlist secret
WRONG = "not-the-password"  # pragma: allowlist secret
PER_MINUTE = 2
T0 = datetime(2026, 11, 3, 12, 0, 10, tzinfo=UTC)
JSON = {"Accept": "application/json"}


@pytest.fixture(autouse=True)
def _cheap_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_passwords, "DEFAULT_ROUNDS", FAST_ROUNDS)


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


@pytest.fixture
def forced(client: TestClient, db: sqlite3.Connection) -> TestClient:
    _flag(db, 1)
    return client


def _form(
    current: str = TEST_PASSWORD, new: str = NEW_PASSWORD, confirm: str | None = None
) -> dict[str, str]:
    return {
        "current_password": current,
        "new_password": new,
        "confirm_password": new if confirm is None else confirm,
    }


def _flag(db: sqlite3.Connection, value: int) -> None:
    db.execute("UPDATE users SET must_change_password = ? WHERE id = 1", (value,))
    db.commit()


def _user(db: sqlite3.Connection) -> sqlite3.Row:
    row: sqlite3.Row = db.execute("SELECT * FROM users WHERE id = 1").fetchone()
    return row


def _next_value(html: str) -> str:
    """The hidden ``next`` carried by the password form (hidden inputs have no role)."""
    form = _html.resolve_one(html, ui.password_form)
    hidden = form.find("input", attrs={"name": "next"})
    assert isinstance(hidden, Tag)
    return str(hidden["value"])


def _post(client: TestClient, current: str = WRONG, **kw: Any) -> Any:
    return client.post("/settings/password", data=_form(current), follow_redirects=False, **kw)


def _burn(client: TestClient) -> None:
    for _ in range(PER_MINUTE):
        assert _post(client).status_code == 422


# --- GET /settings/password ------------------------------------------------


@covers("GET /settings/password")
def test_get_sends_unflagged_user_to_security_tab(client: TestClient) -> None:
    r = client.get("/settings/password", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/settings/security#password"


@covers("GET /settings/password")
def test_get_forced_page_is_standalone_with_banner(forced: TestClient) -> None:
    r = forced.get("/settings/password")
    assert r.status_code == 200
    assert _html.exists(r.text, ui.forced_banner)
    assert _html.exists(r.text, ui.save_and_continue)
    assert _html.exists(r.text, ui.sign_out_instead)
    assert not _html.exists(r.text, ui.tabs)
    assert not _html.exists(r.text, ui.passkeys)
    assert _html.resolve_one(r.text, ui.new_password)["autocomplete"] == "new-password"
    assert _html.resolve_one(r.text, ui.current_password)["autocomplete"] == "current-password"


@covers("GET /settings/password")
def test_get_forced_carries_only_safe_next(forced: TestClient) -> None:
    ok = forced.get("/settings/password?next=/ledger").text
    assert _next_value(ok) == "/ledger"
    evil = forced.get("/settings/password?next=https://evil.test/").text
    assert _next_value(evil) == "/today"


@covers("GET /settings/password")
def test_get_forced_htmx_returns_form_fragment(forced: TestClient) -> None:
    r = forced.get("/settings/password", headers=HX)
    assert r.status_code == 200
    assert "<html" not in r.text
    assert _html.exists(r.text, ui.password_form)


@covers("GET /settings/password")
def test_get_requires_login(anon_client: TestClient) -> None:
    r = anon_client.get("/settings/password", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith("/auth/login")


# --- POST /settings/password -----------------------------------------------


@covers("POST /settings/password")
def test_post_success_rotates_session_revokes_others_and_audits(
    forced: TestClient, db: sqlite3.Connection, session_cookie: tuple[str, str]
) -> None:
    other = issue_session(db)
    r = forced.post(
        "/settings/password", data={**_form(), "next": "/ledger"}, follow_redirects=False
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/ledger"
    assert any(h.startswith(session_cookie[0] + "=") for h in r.headers.get_list("set-cookie"))
    row = _user(db)
    assert row["must_change_password"] == 0
    assert _passwords.verify_password(NEW_PASSWORD, row["password_hash"])
    assert sessions_repo.get_session(db, session_cookie[1]) is None  # token rotated
    assert sessions_repo.list_active_sessions(db, 1)
    assert sessions_repo.get_session(db, other) is None
    assert forced.get("/accounts", follow_redirects=False).status_code == 200


@covers("POST /settings/password")
def test_post_success_htmx_uses_hx_redirect(client: TestClient) -> None:
    htmx = client.post("/settings/password", data=_form(), headers=HX)
    assert htmx.status_code == 204
    assert htmx.headers["HX-Redirect"] == "/settings/security"


@covers("POST /settings/password")
def test_post_next_password_path_falls_back_to_today(
    forced: TestClient,
) -> None:
    r = forced.post(
        "/settings/password",
        data={**_form(), "next": "/settings/password"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/today"


@covers("POST /settings/password")
def test_post_wrong_current_is_422_audited_and_changes_nothing(
    forced: TestClient, db: sqlite3.Connection
) -> None:
    before = _user(db)["password_hash"]
    r = forced.post("/settings/password", data=_form(current=WRONG), headers={"User-Agent": "ua"})
    assert r.status_code == 422
    assert _html.resolve_one(r.text, ui.current_password)["aria-invalid"] == "true"
    assert WRONG not in r.text
    row = _user(db)
    assert row["password_hash"] == before
    assert row["must_change_password"] == 1
    audit = db.execute(
        "SELECT * FROM audit_log WHERE entity_type = 'auth_event' ORDER BY id DESC"
    ).fetchone()
    assert json.loads(audit["new_json"])["event"] == "password_change_failed"
    assert (audit["user_id"], audit["user_agent"]) == (1, "ua")
    assert audit["ip"] is not None
    assert audit["session_id"] is not None


@covers("POST /settings/password")
@pytest.mark.parametrize(
    ("form", "bad_field"),
    [
        (_form(confirm="something-else-entirely"), "confirm"),
        (_form(new="short"), "new"),
        (_form(new="z" * 73), "new"),
        (_form(new=TEST_PASSWORD), "new"),
    ],
)
def test_post_policy_errors_render_security_page_inline(
    client: TestClient, db: sqlite3.Connection, form: dict[str, str], bad_field: str
) -> None:
    before = _user(db)["password_hash"]
    r = client.post("/settings/password", data=form)
    assert r.status_code == 422
    assert _html.exists(r.text, ui.password_summary)
    assert _html.exists(r.text, ui.tabs)  # unflagged users stay inside Settings
    control = ui.confirm_password if bad_field == "confirm" else ui.new_password
    assert _html.resolve_one(r.text, control)["aria-invalid"] == "true"
    assert _user(db)["password_hash"] == before


@covers("POST /settings/password")
def test_post_error_htmx_returns_form_fragment(client: TestClient) -> None:
    r = client.post("/settings/password", data=_form(new="short"), headers=HX)
    assert r.status_code == 422
    assert "<html" not in r.text
    assert _html.exists(r.text, ui.password_form)
    assert _html.exists(r.text, ui.password_summary)


@covers("POST /settings/password")
def test_post_requires_csrf_and_login(
    raw_client: TestClient, anon_client: TestClient, db: sqlite3.Connection
) -> None:
    before = _user(db)["password_hash"]
    assert raw_client.post("/settings/password", data=_form()).status_code == 403
    anon = anon_client.post("/settings/password", data=_form(), follow_redirects=False)
    assert anon.status_code in {302, 401}
    assert _user(db)["password_hash"] == before


# --- rate limit (T-D18a, ADR-0072) -----------------------------------------


@covers("POST /settings/password")
def test_limit_fires_429_with_retry_after_and_throttled_marker(
    client: TestClient, clock: _Clock
) -> None:
    _burn(client)
    r = _post(client)
    assert r.status_code == 429
    assert r.headers["retry-after"] == "50"
    assert THROTTLED_FORM_ERROR in _html.text_of(r.text, ui.password_summary)
    assert _html.resolve_one(r.text, ui.password_summary).has_attr("data-throttled")


@covers("POST /settings/password")
def test_throttled_correct_password_is_not_applied_and_skips_verify(
    client: TestClient, clock: _Clock, db: sqlite3.Connection
) -> None:
    _burn(client)
    before = _user(db)["password_hash"]
    assert _post(client, TEST_PASSWORD).status_code == 429
    assert _user(db)["password_hash"] == before
    failed = db.execute(
        "SELECT COUNT(*) FROM audit_log WHERE new_json LIKE '%password_change_failed%'"
    ).fetchone()[0]
    assert failed == PER_MINUTE


@covers("POST /settings/password")
def test_throttled_htmx_and_json_shapes(client: TestClient, clock: _Clock) -> None:
    _burn(client)
    hx = _post(client, headers=HX)
    assert hx.status_code == 429
    assert "<html" not in hx.text
    assert _html.exists(hx.text, ui.password_form)
    js = _post(client, headers=JSON)
    assert js.status_code == 429
    assert js.json() == {"error": "rate_limited"}
    assert js.headers["retry-after"] == "50"


@covers("POST /settings/password")
def test_throttled_attempt_audited_and_window_resets(
    client: TestClient, clock: _Clock, db: sqlite3.Connection
) -> None:
    _burn(client)
    assert _post(client).status_code == 429
    rows = db.execute(
        "SELECT entity_id, new_json FROM audit_log WHERE entity_type = 'auth_event'"
    ).fetchall()
    throttled = [(r[0], json.loads(r[1])) for r in rows if "rate_limited" in r[1]]
    assert throttled == [(1, {"event": "rate_limited", "scope": "password_change"})]
    clock.now = T0 + timedelta(seconds=50)
    assert _post(client).status_code == 422


@covers("POST /settings/password")
def test_limit_is_per_user(client: TestClient, clock: _Clock, settings: Settings) -> None:
    _burn(client)
    assert _post(client).status_code == 429
    name, value = login_cookie(settings, user_id=2, email="second@example.test")
    client.cookies.delete(name)
    client.cookies.set(name, value)
    assert _post(client).status_code == 422
