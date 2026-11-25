"""T-UR20a: invite landing pages and invite management on ``/settings/users``.

ADR-0134 section 1 and 10, ADR-0148. ``admin_client`` is user 1 promoted to admin, ``client``
is user 1 as a member, ``anon_client`` has no session. Email stays off (Q9): the link is shown
to the admin once and only ``sha256(token)`` is stored.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.adapters.entropy import SecretsTokenSource
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.services import invites as invites_service
from budget_planner.services.invites import INVITE_LIFETIME
from budget_planner.services.password_change import MSG_TOO_SHORT
from budget_planner.services.setup import MSG_CONFIRM_MISMATCH
from budget_planner.services.users import DUPLICATE_EMAIL_MESSAGE, INVALID_EMAIL_MESSAGE
from budget_planner.web.auth_cookies import SESSION_COOKIE_NAME
from tests.auth_support import FAST_HASHER, TEST_EMAIL
from tests.ui_map import _html, auth, settings as ui

HX = {"HX-Request": "true"}
SHORT_VALUE = "-".join(("too", "short"))
ORIGIN = "https://budget.example.test"
NEW_EMAIL = "accountant@example.test"
NEW_PASSWORD = "-".join(("a", "fresh", "passphrase"))  # pragma: allowlist secret
STATE_EXPIRED = "This invite link has expired. Ask an admin to resend it."
STATE_USED = "This invite has already been used. Sign in with the account it created."
STATE_INVALID = "This link isn\u2019t valid. Ask an admin to resend the invite."
INVITE_AUDIT = (
    "SELECT operation FROM audit_log WHERE entity_type = 'invites' AND entity_id = ? ORDER BY id"
)
ADMIN_PATHS = (
    ("GET", "/settings/users/invites/new"),
    ("POST", "/settings/users/invites"),
    ("GET", "/settings/users/invites/1/revoke"),
    ("POST", "/settings/users/invites/1/resend"),
    ("POST", "/settings/users/invites/1/revoke"),
)


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _create(admin_client: TestClient, email: str = NEW_EMAIL, role: str = "member") -> str:
    """Create through the dialog route; returns the plain token from the link."""
    resp = admin_client.post(
        "/settings/users/invites", data={"email": email, "role": role}, headers=HX
    )
    assert resp.status_code == 200, resp.text
    link = _html.text_of(resp.text, ui.invite_link_value).strip()
    prefix = f"{ORIGIN}/invite/"
    assert link.startswith(prefix) or link.startswith("/invite/") or "/invite/" in link
    return link.rsplit("/invite/", 1)[1]


def _invite_row(db: sqlite3.Connection, email: str = NEW_EMAIL) -> sqlite3.Row:
    row: sqlite3.Row | None = db.execute(
        "SELECT * FROM invites WHERE email = ?", (email,)
    ).fetchone()
    assert row is not None
    return row


def _past_invite(db: sqlite3.Connection, *, email: str, age: timedelta) -> str:
    """An invite created ``age`` ago through the service; returns the plain token."""
    issued = invites_service.create_invite(
        db, 1, email=email, is_admin=False, tokens=SecretsTokenSource(), now=clock.utc_now() - age
    )
    return issued.token


def _accept_form(**over: str) -> dict[str, str]:
    base = {"name": "Ola", "password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD}
    return {**base, **over}


# --- admin: create -------------------------------------------------------------------------


def test_create_stores_hash_only_and_shows_the_link_once(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    resp = admin_client.post(
        "/settings/users/invites",
        data={"email": " Accountant@Example.TEST ", "role": "admin"},
        headers=HX,
    )
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"
    assert resp.headers["hx-retarget"] == "#modal-root"
    token = _html.text_of(resp.text, ui.invite_link_value).strip().rsplit("/invite/", 1)[1]

    row = _invite_row(db)
    assert (row["email"], row["is_admin"], row["invited_by"]) == (NEW_EMAIL, 1, 1)
    assert row["token_hash"] == _sha(token)
    assert token not in json.dumps(dict(row))
    created = datetime.fromisoformat(row["created_at"])
    assert (
        datetime.fromisoformat(row["expires_at"]) - created == INVITE_LIFETIME == timedelta(days=7)
    )
    assert [a["operation"] for a in db.execute(INVITE_AUDIT, (row["id"],))] == ["create"]
    audit_new = db.execute(
        "SELECT new_json, actor_user_id FROM audit_log WHERE entity_type = 'invites'"
    ).fetchone()
    assert audit_new["actor_user_id"] == 1
    assert token not in audit_new["new_json"]
    assert _sha(token) not in audit_new["new_json"]
    # the table refreshed out of band carries the pending row
    assert _html.exists(resp.text, ui.invite_row(row["id"]))
    assert _html.count(resp.text, ui.invite_link_dialog) == 1
    assert _html.exists(resp.text, ui.invite_link_value)


def test_roster_lists_pending_and_expired_invites_not_revoked_or_used(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    pending_token = _create(admin_client, "pending@example.test")
    expired_token = _past_invite(db, email="old@example.test", age=timedelta(days=8))
    used = invites_service.create_invite(
        db,
        1,
        email="used@example.test",
        is_admin=False,
        tokens=SecretsTokenSource(),
        now=clock.utc_now(),
    )
    invites_service.accept_invite(
        db, used.token, name="U", password=NEW_PASSWORD, hasher=FAST_HASHER, now=clock.utc_now()
    )
    revoked = invites_service.create_invite(
        db,
        1,
        email="gone@example.test",
        is_admin=False,
        tokens=SecretsTokenSource(),
        now=clock.utc_now(),
    )
    invites_service.revoke_invite(db, 1, revoked.invite.id, now=clock.utc_now())
    assert pending_token and expired_token

    page = admin_client.get("/settings/users")
    assert page.status_code == 200
    ids = {r["email"]: r["id"] for r in db.execute("SELECT id, email FROM invites")}
    for listed in ("pending@example.test", "old@example.test"):
        assert _html.exists(page.text, ui.invite_row(ids[listed])), listed
    for absent in ("used@example.test", "gone@example.test"):
        assert not _html.exists(page.text, ui.invite_row(ids[absent])), absent
    assert _html.count(page.text, ui.any_invite_row) == 2
    expired_row = _html.text_of(page.text, ui.invite_row(ids["old@example.test"]))
    pending_row = _html.text_of(page.text, ui.invite_row(ids["pending@example.test"]))
    expires = datetime.fromisoformat(
        db.execute(
            "SELECT expires_at FROM invites WHERE email = 'pending@example.test'"
        ).fetchone()[0]
    )
    stamp = expires.astimezone(ZoneInfo("Europe/Warsaw")).strftime("%d %b").upper()
    assert f"✉ invited · expires {stamp}" in pending_row
    assert "✉ invite expired" in expired_row
    assert _html.exists(page.text, ui.create_invite_link)


def test_create_refuses_bad_duplicate_and_pending_emails(
    admin_client: TestClient, db: sqlite3.Connection
) -> None:
    bad = admin_client.post(
        "/settings/users/invites", data={"email": "nope", "role": "member"}, headers=HX
    )
    assert bad.status_code == 422
    assert (
        _html.text_of(bad.text, ui.invite_email_error).strip() == f"\u25b2 {INVALID_EMAIL_MESSAGE}"
    )
    assert _html.exists(bad.text, ui.create_invite_dialog)

    user = admin_client.post(
        "/settings/users/invites", data={"email": TEST_EMAIL, "role": "member"}, headers=HX
    )
    assert user.status_code == 422
    assert (
        _html.text_of(user.text, ui.invite_email_error).strip()
        == f"\u25b2 {DUPLICATE_EMAIL_MESSAGE}"
    )

    _create(admin_client)
    again = admin_client.post(
        "/settings/users/invites", data={"email": NEW_EMAIL, "role": "member"}, headers=HX
    )
    assert again.status_code == 422
    pending_error = _html.text_of(again.text, ui.invite_email_error).strip()
    assert pending_error == f"\u25b2 {invites_service.PENDING_INVITE_MESSAGE}"
    assert db.execute("SELECT count(*) FROM invites").fetchone()[0] == 1


def test_create_dialog_opens(admin_client: TestClient) -> None:
    resp = admin_client.get("/settings/users/invites/new", headers=HX)
    assert resp.status_code == 200
    assert resp.headers["hx-retarget"] == "#modal-root"
    assert _html.exists(resp.text, ui.invite_email_field)
    assert _html.exists(resp.text, ui.invite_role_admin)
    assert _html.exists(resp.text, ui.invite_submit)


# --- admin: resend and revoke ----------------------------------------------------------------


def test_resend_rotates_the_link_and_the_old_one_stops_working(
    admin_client: TestClient, anon_client: TestClient, db: sqlite3.Connection
) -> None:
    old = _create(admin_client)
    row = _invite_row(db)
    resp = admin_client.post(f"/settings/users/invites/{row['id']}/resend", headers=HX)
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"
    new = _html.text_of(resp.text, ui.invite_link_value).strip().rsplit("/invite/", 1)[1]
    assert new != old
    after = _invite_row(db)
    assert after["token_hash"] == _sha(new)
    assert [a["operation"] for a in db.execute(INVITE_AUDIT, (row["id"],))] == ["create", "update"]

    assert (
        _html.text_of(anon_client.get(f"/invite/{old}").text, auth.invite_alert).strip()
        == f"▲ {STATE_INVALID}"
    )
    assert _html.exists(anon_client.get(f"/invite/{new}").text, auth.invite_create)


def test_revoke_confirm_then_link_reads_invalid_and_row_leaves(
    admin_client: TestClient, anon_client: TestClient, db: sqlite3.Connection
) -> None:
    token = _create(admin_client)
    invite_id = _invite_row(db)["id"]
    confirm = admin_client.get(f"/settings/users/invites/{invite_id}/revoke", headers=HX)
    assert confirm.status_code == 200
    assert _html.exists(confirm.text, ui.revoke_invite_confirm)

    done = admin_client.post(f"/settings/users/invites/{invite_id}/revoke", headers=HX)
    assert done.status_code == 200
    assert (
        _html.text_of(done.text, ui.flash_success).strip()
        == "\u25cf Revoked the invite for accountant@example.test."
    )
    assert _invite_row(db)["revoked_at"] is not None
    assert [a["operation"] for a in db.execute(INVITE_AUDIT, (invite_id,))] == ["create", "update"]
    assert (
        _html.text_of(anon_client.get(f"/invite/{token}").text, auth.invite_alert).strip()
        == f"▲ {STATE_INVALID}"
    )
    assert not _html.exists(admin_client.get("/settings/users").text, ui.invite_row(invite_id))

    again = admin_client.post(f"/settings/users/invites/{invite_id}/revoke", headers=HX)
    assert again.status_code == 409
    flash = _html.text_of(again.text, ui.flash_error_region)
    assert flash.strip().startswith(f"\u25b2 {invites_service.INVITE_FINAL_MESSAGE}")
    assert _html.exists(again.text, ui.flash_error_close)
    resend = admin_client.post(f"/settings/users/invites/{invite_id}/resend", headers=HX)
    assert resend.status_code == 409


def test_unknown_invite_is_404(admin_client: TestClient) -> None:
    assert admin_client.get("/settings/users/invites/999/revoke", headers=HX).status_code == 404
    missing = admin_client.post("/settings/users/invites/999/resend", headers=HX)
    assert missing.status_code == 404
    assert (
        _html.text_of(missing.text, ui.flash_error_region)
        .strip()
        .startswith("\u25b2 Invite not found")
    )
    assert _html.exists(missing.text, ui.flash_error_close)
    assert admin_client.post("/settings/users/invites/999/revoke", headers=HX).status_code == 404


@pytest.mark.parametrize(("method", "path"), ADMIN_PATHS)
def test_non_admin_is_refused_and_nothing_is_written(
    client: TestClient, db: sqlite3.Connection, method: str, path: str
) -> None:
    resp = client.request(method, path, data={"email": NEW_EMAIL, "role": "member"}, headers=HX)
    assert resp.status_code == 404
    assert db.execute("SELECT count(*) FROM invites").fetchone()[0] == 0


def test_signed_out_cannot_reach_the_admin_routes(
    anon_client: TestClient, db: sqlite3.Connection
) -> None:
    resp = anon_client.post(
        "/settings/users/invites", data={"email": NEW_EMAIL, "role": "member"}, headers=HX
    )
    assert resp.status_code in {303, 401}
    assert db.execute("SELECT count(*) FROM invites").fetchone()[0] == 0


# --- landing: states -------------------------------------------------------------------------


def test_pending_link_shows_the_accept_form(
    admin_client: TestClient, anon_client: TestClient
) -> None:
    token = _create(admin_client, role="admin")
    page = anon_client.get(f"/invite/{token}")
    assert page.status_code == 200
    assert _html.exists(page.text, auth.invite_heading)
    assert _html.text_of(page.text, auth.invite_caption).strip() == f"invited by {TEST_EMAIL}"
    email = _html.resolve_one(page.text, auth.invite_email)
    assert email.get("value") == NEW_EMAIL
    assert email.has_attr("readonly")
    for field in (auth.invite_name, auth.invite_password, auth.invite_confirm, auth.invite_create):
        assert _html.exists(page.text, field)
    assert not _html.exists(page.text, auth.invite_alert)


def test_expired_used_and_invalid_links_show_their_state(
    anon_client: TestClient, db: sqlite3.Connection
) -> None:
    expired = _past_invite(db, email="old@example.test", age=INVITE_LIFETIME + timedelta(minutes=1))
    used_tok = _past_invite(db, email="used@example.test", age=timedelta(hours=1))
    invites_service.accept_invite(
        db, used_tok, name="U", password=NEW_PASSWORD, hasher=FAST_HASHER, now=clock.utc_now()
    )
    cases = {expired: STATE_EXPIRED, used_tok: STATE_USED, "not-a-token": STATE_INVALID}
    for token, message in cases.items():
        page = anon_client.get(f"/invite/{token}")
        assert page.status_code == 200
        assert _html.text_of(page.text, auth.invite_alert).strip() == f"▲ {message}"
        assert _html.exists(page.text, auth.invite_back)
        assert not _html.exists(page.text, auth.invite_create)
        assert not _html.exists(page.text, auth.invite_password)


def test_expired_link_cannot_be_accepted(anon_client: TestClient, db: sqlite3.Connection) -> None:
    expired = _past_invite(db, email="old@example.test", age=timedelta(days=8))
    resp = anon_client.post(f"/invite/{expired}", data=_accept_form(), follow_redirects=False)
    assert resp.status_code == 200
    assert _html.text_of(resp.text, auth.invite_alert).strip() == f"▲ {STATE_EXPIRED}"
    assert (
        db.execute("SELECT count(*) FROM users WHERE email = 'old@example.test'").fetchone()[0] == 0
    )
    assert SESSION_COOKIE_NAME not in resp.headers.get("set-cookie", "")


# --- landing: accept -------------------------------------------------------------------------


def test_accept_creates_the_user_signs_in_and_uses_the_invite(
    admin_client: TestClient, anon_client: TestClient, db: sqlite3.Connection
) -> None:
    token = _create(admin_client, role="admin")
    resp = anon_client.post(f"/invite/{token}", data=_accept_form(), follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/today"
    assert f"{SESSION_COOKIE_NAME}=" in resp.headers["set-cookie"]

    user = db.execute(
        "SELECT id, name, email, is_admin, must_change_password, password_hash "
        "FROM users WHERE email = ?",
        (NEW_EMAIL,),
    ).fetchone()
    assert (user["name"], user["is_admin"], user["must_change_password"]) == ("Ola", 1, 0)
    assert user["password_hash"] != NEW_PASSWORD
    assert FAST_HASHER.verify(NEW_PASSWORD, user["password_hash"])
    invite = _invite_row(db)
    assert invite["used_at"] is not None
    assert [a["operation"] for a in db.execute(INVITE_AUDIT, (invite["id"],))] == [
        "create",
        "update",
    ]
    created = db.execute(
        "SELECT operation FROM audit_log WHERE entity_type = 'users' AND entity_id = ?",
        (user["id"],),
    ).fetchall()
    assert [c["operation"] for c in created] == ["create"]
    # the link now reads used, a second accept is refused and creates nothing more
    used = anon_client.get(f"/invite/{token}")
    assert _html.text_of(used.text, auth.invite_alert).strip() == f"▲ {STATE_USED}"
    again = anon_client.post(
        f"/invite/{token}", data=_accept_form(name="Other"), follow_redirects=False
    )
    assert again.status_code == 200
    assert db.execute("SELECT count(*) FROM users WHERE email = ?", (NEW_EMAIL,)).fetchone()[0] == 1


def test_accept_as_member_creates_a_member(
    admin_client: TestClient, anon_client: TestClient, db: sqlite3.Connection
) -> None:
    token = _create(admin_client)
    assert (
        anon_client.post(
            f"/invite/{token}", data=_accept_form(), follow_redirects=False
        ).status_code
        == 303
    )
    assert db.execute("SELECT is_admin FROM users WHERE email = ?", (NEW_EMAIL,)).fetchone()[0] == 0


def test_accept_errors_show_under_the_field_and_write_nothing(
    admin_client: TestClient, anon_client: TestClient, db: sqlite3.Connection
) -> None:
    token = _create(admin_client)
    short = anon_client.post(
        f"/invite/{token}",
        data=_accept_form(password=SHORT_VALUE, password_confirm=SHORT_VALUE),
        follow_redirects=False,
    )
    assert short.status_code == 422
    assert _html.text_of(short.text, auth.invite_password_error).strip() == f"▲ {MSG_TOO_SHORT}"
    mismatch = anon_client.post(
        f"/invite/{token}",
        data=_accept_form(password_confirm=NEW_PASSWORD + "x"),
        follow_redirects=False,
    )
    assert mismatch.status_code == 422
    assert (
        _html.text_of(mismatch.text, auth.invite_confirm_error).strip()
        == f"▲ {MSG_CONFIRM_MISMATCH}"
    )
    assert _html.resolve_one(mismatch.text, auth.invite_name).get("value") == "Ola"
    assert _html.resolve_one(mismatch.text, auth.invite_password).get("value") is None
    assert db.execute("SELECT count(*) FROM users WHERE email = ?", (NEW_EMAIL,)).fetchone()[0] == 0
    assert _invite_row(db)["used_at"] is None
    assert SESSION_COOKIE_NAME not in mismatch.headers.get("set-cookie", "")


# --- landing: no-store and rate limit (security review) ---------------------------------------


def test_landing_responses_are_no_store(admin_client: TestClient, anon_client: TestClient) -> None:
    token = _create(admin_client)
    assert anon_client.get(f"/invite/{token}").headers["cache-control"] == "no-store"
    assert anon_client.get("/invite/unknown").headers["cache-control"] == "no-store"
    bad = anon_client.post(
        f"/invite/{token}", data=_accept_form(password_confirm=SHORT_VALUE), follow_redirects=False
    )
    assert bad.status_code == 422
    assert bad.headers["cache-control"] == "no-store"


def test_post_is_rate_limited_per_ip_and_audited(
    admin_client: TestClient,
    anon_client: TestClient,
    _migrated: Settings,
    db: sqlite3.Connection,
) -> None:
    limit = 2
    token = _create(admin_client)
    anon_client.app.state.settings = _migrated.model_copy(  # type: ignore[attr-defined]  # test-only swap of the app settings
        update={"rate_limit_login_ip_per_hour": limit}
    )
    for _ in range(limit):
        spent = anon_client.post(
            f"/invite/{token}",
            data=_accept_form(password_confirm=SHORT_VALUE),
            follow_redirects=False,
        )
        assert spent.status_code == 422
    throttled = anon_client.post(f"/invite/{token}", data=_accept_form(), follow_redirects=False)
    assert throttled.status_code == 429
    assert int(throttled.headers["Retry-After"]) > 0
    assert throttled.headers["cache-control"] == "no-store"
    assert _html.exists(throttled.text, auth.invite_alert)
    assert db.execute("SELECT count(*) FROM users WHERE email = ?", (NEW_EMAIL,)).fetchone()[0] == 0
    assert _invite_row(db)["used_at"] is None
    audits = db.execute(
        "SELECT new_json FROM audit_log WHERE entity_type = 'auth_event'"
    ).fetchall()
    assert [json.loads(a["new_json"])["event"] for a in audits] == ["rate_limited"]
