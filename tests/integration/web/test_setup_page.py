"""T-UR21 - first-run /setup page (ADR-0134 section 9, ADR-0148).

Open instance: hash configured, no credentialed user, not consumed. A closed
instance redirects to sign in; an open one without a valid token is a 404
(no oracle). The service itself is covered in ``tests/unit/services/test_setup.py``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.services.setup import hash_token
from budget_planner.web.auth_cookies import SESSION_COOKIE_NAME
from tests.auth_support import TEST_PASSWORD
from tests.db_template import sqlite_url
from tests.ui_map import _html, auth, shell
from tests.ui_map.locator import Locator

pytestmark = pytest.mark.integration

TOKEN = "-".join(("tok", "web", "setup", "value"))
WRONG_TOKEN = "-".join(("not", "the", "token"))
ADMIN_EMAIL = "first.admin@example.test"
ADMIN_NAME = "First Admin"
IP_LIMIT = 2
SETUP_URL = f"/setup?token={TOKEN}"
USERS_WITH_EMAIL = "SELECT COUNT(*) FROM users WHERE email IS NOT NULL"
MARKERS = "SELECT COUNT(*) FROM setup_token_consumed"
MISMATCH = "The two passwords do not match."
BAD_EMAIL = "Enter a full email address"
LOGIN = "/auth/login"
SHORT_VALUE = "-".join(("too", "short"))
OTHER_VALUE = "-".join(("some", "other", "value"))


@pytest.fixture
def settings(migrated_db: Path) -> Settings:
    return Settings(
        _env_file=None,
        env="test",
        cookie_secret="x" * 32,
        webauthn_rp_id="budget.example.test",
        webauthn_origin="https://budget.example.test",
        database_url=sqlite_url(migrated_db),
        planner_setup_token_hash=hash_token(TOKEN),
        rate_limit_login_ip_per_hour=IP_LIMIT,
    )


def _form(**over: str) -> dict[str, str]:
    base = {
        "token": TOKEN,
        "name": ADMIN_NAME,
        "email": ADMIN_EMAIL,
        "password": TEST_PASSWORD,
        "password_confirm": TEST_PASSWORD,
    }
    return {**base, **over}


def _count(conn: sqlite3.Connection, sql: str) -> int:
    return int(conn.execute(sql).fetchone()[0])


def test_get_open_renders_form_with_token_carried(anon_client: TestClient) -> None:
    r = anon_client.get(SETUP_URL)
    assert r.status_code == 200
    assert _html.exists(r.text, auth.setup_heading)
    for loc in (
        auth.setup_name,
        auth.setup_email,
        auth.setup_password,
        auth.setup_confirm,
        auth.setup_create,
    ):
        assert _html.exists(r.text, loc)
    assert _html.resolve_one(r.text, auth.setup_token).get("value") == TOKEN
    assert not _html.exists(r.text, shell.primary_nav)


@pytest.mark.parametrize("url", ["/setup", "/setup?token=wrong-token"])
def test_get_open_without_valid_token_is_404(anon_client: TestClient, url: str) -> None:
    r = anon_client.get(url, follow_redirects=False)
    assert r.status_code == 404
    assert not _html.exists(r.text, auth.setup_heading)


def test_get_closed_when_user_exists_redirects_to_sign_in(
    anon_client: TestClient, conn: sqlite3.Connection
) -> None:
    conn.execute("UPDATE users SET email = 'u@example.test' WHERE id = 1")
    conn.commit()
    r = anon_client.get(SETUP_URL, follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, LOGIN)


def test_get_closed_without_configured_hash_redirects_to_sign_in(
    anon_client: TestClient, settings: Settings
) -> None:
    closed = settings.model_copy(update={"planner_setup_token_hash": None})
    anon_client.app.state.settings = closed  # type: ignore[attr-defined]  # test-only swap of the app settings
    r = anon_client.get(SETUP_URL, follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, LOGIN)


def test_post_wrong_token_is_404_and_writes_nothing(
    anon_client: TestClient, conn: sqlite3.Connection
) -> None:
    r = anon_client.post("/setup", data=_form(token=WRONG_TOKEN), follow_redirects=False)
    assert r.status_code == 404
    assert _count(conn, USERS_WITH_EMAIL) == 0
    assert _count(conn, MARKERS) == 0
    assert SESSION_COOKIE_NAME not in r.headers.get("set-cookie", "")


def test_post_valid_creates_admin_audit_session_and_closes(
    anon_client: TestClient, conn: sqlite3.Connection
) -> None:
    r = anon_client.post("/setup", data=_form(), follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/today"
    assert f"{SESSION_COOKIE_NAME}=" in r.headers["set-cookie"]

    row = conn.execute(
        "SELECT id, name, email, is_admin, must_change_password FROM users WHERE email = ?",
        (ADMIN_EMAIL,),
    ).fetchone()
    assert (row["name"], row["email"], row["is_admin"], row["must_change_password"]) == (
        ADMIN_NAME,
        ADMIN_EMAIL,
        1,
        0,
    )
    assert _count(conn, MARKERS) == 1
    audit = conn.execute(
        "SELECT operation, new_json FROM audit_log WHERE entity_type = 'setup_token'"
    ).fetchall()
    assert [a["operation"] for a in audit] == ["create"]
    assert json.loads(audit[0]["new_json"])["user_id"] == row["id"]
    assert TOKEN not in audit[0]["new_json"]

    # signed in as the new admin, and setup is closed afterwards
    assert anon_client.get("/today", follow_redirects=False).status_code == 200
    again = anon_client.get(SETUP_URL, follow_redirects=False)
    assert (again.status_code, again.headers["location"]) == (303, LOGIN)


def test_second_post_after_completion_is_refused(
    anon_client: TestClient, conn: sqlite3.Connection
) -> None:
    assert anon_client.post("/setup", data=_form(), follow_redirects=False).status_code == 303
    r = anon_client.post("/setup", data=_form(email="second@example.test"), follow_redirects=False)
    assert (r.status_code, r.headers["location"]) == (303, LOGIN)
    assert _count(conn, USERS_WITH_EMAIL) == 1
    assert _count(conn, MARKERS) == 1


@pytest.mark.parametrize(
    ("over", "error_loc", "message"),
    [
        ({"email": "not-an-email"}, auth.setup_email_error, BAD_EMAIL),
        (
            {"password": SHORT_VALUE, "password_confirm": SHORT_VALUE},
            auth.setup_password_error,
            "12 characters",
        ),
        ({"password_confirm": OTHER_VALUE}, auth.setup_confirm_error, MISMATCH),
    ],
)
def test_post_invalid_input_is_422_with_field_error_and_token_kept(
    anon_client: TestClient,
    conn: sqlite3.Connection,
    over: dict[str, str],
    error_loc: Locator,
    message: str,
) -> None:
    r = anon_client.post("/setup", data=_form(**over), follow_redirects=False)
    assert r.status_code == 422
    assert message in _html.text_of(r.text, error_loc)
    assert _html.resolve_one(r.text, auth.setup_token).get("value") == TOKEN
    assert _count(conn, USERS_WITH_EMAIL) == 0
    assert _count(conn, MARKERS) == 0
    for field in (auth.setup_password, auth.setup_confirm):  # never echoed back
        assert _html.resolve_one(r.text, field).get("value") is None


def test_post_is_rate_limited_per_ip_before_the_token_is_checked(
    anon_client: TestClient, conn: sqlite3.Connection
) -> None:
    for _ in range(IP_LIMIT):
        assert anon_client.post("/setup", data=_form(token=WRONG_TOKEN)).status_code == 404
    r = anon_client.post("/setup", data=_form())
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
    assert _html.exists(r.text, auth.setup_alert)
    assert _count(conn, USERS_WITH_EMAIL) == 0


def test_post_without_valid_csrf_is_403_and_writes_nothing(
    anon_client: TestClient, conn: sqlite3.Connection
) -> None:
    r = anon_client.post(
        "/setup", data=_form(), headers={"X-CSRF-Token": "forged"}, follow_redirects=False
    )
    assert r.status_code == 403
    assert _count(conn, USERS_WITH_EMAIL) == 0
