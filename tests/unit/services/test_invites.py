"""T-UR30: invite data layer (ADR-0134 section 1 and 10, ADR-0019, ADR-0022)."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories import invites as invites_repo
from budget_planner.services import invites as invites_service
from budget_planner.services.invites import (
    INVITE_LIFETIME,
    InviteConflictError,
    InviteNotFoundError,
    IssuedInvite,
    accept_invite,
    create_invite,
    invite_state,
    link_state,
    list_invites,
    resend_invite,
    revoke_invite,
)
from budget_planner.services.users import (
    DUPLICATE_EMAIL_MESSAGE,
    INVALID_EMAIL_MESSAGE,
    UserInputError,
)
from tests.auth_support import FAKE_HASHER, FakeTokenSource

ADMIN_ID = 1
PW = "pw"
PW_CHOSEN = "s3cret"
PW_EMPTY = ""
TOK1 = "tok-1-32"
TOK2 = "tok-2-32"
NOW = datetime(2026, 11, 20, 9, 30, 15, 250000, tzinfo=UTC)
CTX = RequestCtx(ip="127.0.0.1", user_id=ADMIN_ID, session_id="h", user_agent="pytest")


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _issue(
    conn: sqlite3.Connection, tokens: FakeTokenSource, email: str = "new@example.test"
) -> IssuedInvite:
    return create_invite(
        conn, ADMIN_ID, email=email, is_admin=False, tokens=tokens, now=NOW, request_ctx=CTX
    )


def _audit(conn: sqlite3.Connection, invite_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM audit_log WHERE entity_type = 'invites' AND entity_id = ? ORDER BY id",
        (invite_id,),
    ).fetchall()


def test_lifetime_is_seven_days() -> None:
    assert timedelta(days=7) == INVITE_LIFETIME


def test_create_stores_exact_row_and_audit(conn: sqlite3.Connection) -> None:
    issued = create_invite(
        conn,
        ADMIN_ID,
        email="  New@Example.TEST ",
        is_admin=True,
        tokens=FakeTokenSource(),
        now=NOW,
        request_ctx=CTX,
    )

    assert issued.token == TOK1
    row = conn.execute("SELECT * FROM invites").fetchone()
    assert row["email"] == "new@example.test"
    assert row["is_admin"] == 1
    assert row["invited_by"] == ADMIN_ID
    assert row["token_hash"] == _sha("tok-1-32")
    assert row["created_at"] == "2026-11-20T09:30:15.250Z"
    assert row["updated_at"] == "2026-11-20T09:30:15.250Z"
    assert row["expires_at"] == "2026-11-27T09:30:15.250Z"
    assert (row["used_at"], row["revoked_at"], row["deleted_at"]) == (None, None, None)
    audit = _audit(conn, issued.invite.id)
    assert [a["operation"] for a in audit] == ["create"]
    assert audit[0]["prev_json"] is None
    assert json.loads(audit[0]["new_json"]) == {
        "id": issued.invite.id,
        "email": "new@example.test",
        "is_admin": True,
        "invited_by": ADMIN_ID,
        "created_at": "2026-11-20T09:30:15.250Z",
        "expires_at": "2026-11-27T09:30:15.250Z",
        "used_at": None,
        "revoked_at": None,
    }
    assert audit[0]["actor_user_id"] == ADMIN_ID
    assert audit[0]["user_id"] == ADMIN_ID
    assert audit[0]["ip"] == "127.0.0.1"


def test_create_refuses_invalid_email(conn: sqlite3.Connection) -> None:
    with pytest.raises(UserInputError) as err:
        _issue(conn, FakeTokenSource(), email="nope")
    assert err.value.fields == {"email": INVALID_EMAIL_MESSAGE}
    assert conn.execute("SELECT count(*) FROM invites").fetchone()[0] == 0


def test_create_refuses_live_user_email(conn: sqlite3.Connection) -> None:
    conn.execute("UPDATE users SET email = 'root@example.test' WHERE id = ?", (ADMIN_ID,))
    with pytest.raises(UserInputError) as err:
        _issue(conn, FakeTokenSource(), email="ROOT@example.test")
    assert err.value.fields == {"email": DUPLICATE_EMAIL_MESSAGE}
    assert conn.execute("SELECT count(*) FROM invites").fetchone()[0] == 0


def test_create_refuses_pending_invite_email(conn: sqlite3.Connection) -> None:
    tokens = FakeTokenSource()
    _issue(conn, tokens)
    with pytest.raises(UserInputError) as err:
        _issue(conn, tokens, email="NEW@example.test")
    assert err.value.fields == {"email": invites_service.PENDING_INVITE_MESSAGE}
    assert conn.execute("SELECT count(*) FROM invites").fetchone()[0] == 1


def test_create_allowed_after_expiry_revoke_and_use(conn: sqlite3.Connection) -> None:
    tokens = FakeTokenSource()
    first = _issue(conn, tokens)
    later = NOW + INVITE_LIFETIME  # exactly expired
    create_invite(
        conn, ADMIN_ID, email="new@example.test", is_admin=False, tokens=tokens, now=later
    )
    revoke_invite(conn, ADMIN_ID, first.invite.id, now=NOW)
    assert conn.execute("SELECT count(*) FROM invites").fetchone()[0] == 2


def test_resend_rotates_token_and_expiry_and_kills_old_token(conn: sqlite3.Connection) -> None:
    tokens = FakeTokenSource()
    first = _issue(conn, tokens)
    later = NOW + timedelta(days=3)

    second = resend_invite(
        conn, ADMIN_ID, first.invite.id, tokens=tokens, now=later, request_ctx=CTX
    )

    assert second.token == TOK2
    row = conn.execute("SELECT * FROM invites").fetchone()
    assert row["token_hash"] == _sha("tok-2-32")
    assert row["created_at"] == "2026-11-20T09:30:15.250Z"
    assert row["updated_at"] == "2026-11-23T09:30:15.250Z"
    assert row["expires_at"] == "2026-11-30T09:30:15.250Z"
    assert link_state(conn, first.token, now=later) == "invalid"
    assert link_state(conn, second.token, now=later) == "pending"
    audit = _audit(conn, first.invite.id)
    assert [a["operation"] for a in audit] == ["create", "update"]
    assert json.loads(audit[1]["prev_json"])["expires_at"] == "2026-11-27T09:30:15.250Z"
    assert json.loads(audit[1]["new_json"])["expires_at"] == "2026-11-30T09:30:15.250Z"
    assert "token_hash" not in audit[1]["new_json"]


def test_resend_revives_an_expired_invite(conn: sqlite3.Connection) -> None:
    tokens = FakeTokenSource()
    first = _issue(conn, tokens)
    late = NOW + timedelta(days=10)
    assert link_state(conn, first.token, now=late) == "expired"
    second = resend_invite(conn, ADMIN_ID, first.invite.id, tokens=tokens, now=late)
    assert link_state(conn, second.token, now=late) == "pending"


def test_resend_refused_on_revoked_and_used(conn: sqlite3.Connection) -> None:
    tokens = FakeTokenSource()
    revoked = _issue(conn, tokens, email="a@example.test")
    revoke_invite(conn, ADMIN_ID, revoked.invite.id, now=NOW)
    used = _issue(conn, tokens, email="b@example.test")
    accept_invite(conn, used.token, name="B", password=PW, hasher=FAKE_HASHER, now=NOW)

    for invite_id in (revoked.invite.id, used.invite.id):
        with pytest.raises(InviteConflictError) as err:
            resend_invite(conn, ADMIN_ID, invite_id, tokens=tokens, now=NOW)
        assert err.value.message == invites_service.INVITE_FINAL_MESSAGE
    assert conn.execute(
        "SELECT token_hash FROM invites WHERE id = ?", (revoked.invite.id,)
    ).fetchone()[0] == _sha(revoked.token)


def test_resend_and_revoke_unknown_invite(conn: sqlite3.Connection) -> None:
    with pytest.raises(InviteNotFoundError):
        resend_invite(conn, ADMIN_ID, 999, tokens=FakeTokenSource(), now=NOW)
    with pytest.raises(InviteNotFoundError):
        revoke_invite(conn, ADMIN_ID, 999, now=NOW)


def test_revoke_is_final(conn: sqlite3.Connection) -> None:
    tokens = FakeTokenSource()
    issued = _issue(conn, tokens)
    at = NOW + timedelta(hours=1)

    revoked = revoke_invite(conn, ADMIN_ID, issued.invite.id, now=at, request_ctx=CTX)

    assert revoked.revoked_at == at
    row = conn.execute("SELECT * FROM invites").fetchone()
    assert row["revoked_at"] == "2026-11-20T10:30:15.250Z"
    assert link_state(conn, issued.token, now=at) == "invalid"
    audit = _audit(conn, issued.invite.id)
    assert [a["operation"] for a in audit] == ["create", "update"]
    assert json.loads(audit[1]["new_json"])["revoked_at"] == "2026-11-20T10:30:15.250Z"
    with pytest.raises(InviteConflictError):
        revoke_invite(conn, ADMIN_ID, issued.invite.id, now=at)
    with pytest.raises(InviteConflictError):
        resend_invite(conn, ADMIN_ID, issued.invite.id, tokens=tokens, now=at)
    with pytest.raises(InviteConflictError):
        accept_invite(conn, issued.token, name="x", password=PW, hasher=FAKE_HASHER, now=at)


def test_accept_creates_user_marks_used_and_audits(conn: sqlite3.Connection) -> None:
    issued = create_invite(
        conn,
        ADMIN_ID,
        email="new@example.test",
        is_admin=True,
        tokens=FakeTokenSource(),
        now=NOW,
    )
    at = NOW + timedelta(days=1)

    user = accept_invite(
        conn, issued.token, name="  Newcomer  ", password=PW_CHOSEN, hasher=FAKE_HASHER, now=at
    )

    row = conn.execute("SELECT * FROM users WHERE id = ?", (user.id,)).fetchone()
    assert (row["email"], row["name"], row["is_admin"]) == ("new@example.test", "Newcomer", 1)
    assert row["password_hash"] == FAKE_HASHER.hash(PW_CHOSEN)
    assert row["must_change_password"] == 0
    inv = conn.execute("SELECT * FROM invites").fetchone()
    assert inv["used_at"] == "2026-11-21T09:30:15.250Z"
    audit = _audit(conn, issued.invite.id)
    assert [a["operation"] for a in audit] == ["create", "update"]
    assert audit[1]["actor_user_id"] == user.id
    assert link_state(conn, issued.token, now=at) == "used"
    with pytest.raises(InviteConflictError):
        accept_invite(conn, issued.token, name="x", password=PW, hasher=FAKE_HASHER, now=at)
    assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 2


def test_accept_member_role_and_name_fallback(conn: sqlite3.Connection) -> None:
    issued = _issue(conn, FakeTokenSource())
    user = accept_invite(conn, issued.token, name="", password=PW, hasher=FAKE_HASHER, now=NOW)
    assert (user.email, user.name, user.is_admin) == ("new@example.test", "new", False)


def test_accept_failure_persists_nothing(conn: sqlite3.Connection) -> None:
    issued = _issue(conn, FakeTokenSource())
    users_before = conn.execute("SELECT count(*) FROM users").fetchone()[0]
    audit_before = conn.execute("SELECT count(*) FROM audit_log").fetchone()[0]

    with pytest.raises(UserInputError):  # empty credential: raised after nothing is written
        accept_invite(conn, issued.token, name="n", password=PW_EMPTY, hasher=FAKE_HASHER, now=NOW)
    assert not conn.in_transaction

    # A live user took the email after the invite: the user insert fails inside the transaction.
    conn.execute("UPDATE users SET email = 'new@example.test' WHERE id = ?", (ADMIN_ID,))
    with pytest.raises(UserInputError):
        accept_invite(conn, issued.token, name="n", password=PW, hasher=FAKE_HASHER, now=NOW)

    assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == users_before
    assert conn.execute("SELECT used_at FROM invites").fetchone()[0] is None
    assert conn.execute("SELECT count(*) FROM audit_log").fetchone()[0] == audit_before


def test_accept_rolls_back_user_when_marking_used_fails(
    conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    issued = _issue(conn, FakeTokenSource())

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("mark_used failed")

    monkeypatch.setattr(invites_repo, "mark_used", boom)
    with pytest.raises(RuntimeError):
        accept_invite(conn, issued.token, name="n", password=PW, hasher=FAKE_HASHER, now=NOW)

    assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 1
    assert conn.execute("SELECT used_at FROM invites").fetchone()[0] is None
    assert (
        conn.execute(
            "SELECT count(*) FROM audit_log WHERE entity_type = 'users' AND operation = 'create'"
        ).fetchone()[0]
        == 0
    )


def test_accept_refused_when_expired(conn: sqlite3.Connection) -> None:
    issued = _issue(conn, FakeTokenSource())
    with pytest.raises(InviteConflictError):
        accept_invite(
            conn,
            issued.token,
            name="n",
            password=PW,
            hasher=FAKE_HASHER,
            now=NOW + INVITE_LIFETIME,
        )
    assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 1


def test_link_state_every_case(conn: sqlite3.Connection) -> None:
    tokens = FakeTokenSource()
    pending = _issue(conn, tokens, email="p@example.test")
    expiring = _issue(conn, tokens, email="e@example.test")
    revoked = _issue(conn, tokens, email="r@example.test")
    used = _issue(conn, tokens, email="u@example.test")
    revoke_invite(conn, ADMIN_ID, revoked.invite.id, now=NOW)
    accept_invite(conn, used.token, name="U", password=PW, hasher=FAKE_HASHER, now=NOW)
    just_before = NOW + INVITE_LIFETIME - timedelta(milliseconds=1)

    assert link_state(conn, pending.token, now=just_before) == "pending"
    assert link_state(conn, expiring.token, now=NOW + INVITE_LIFETIME) == "expired"
    assert link_state(conn, revoked.token, now=NOW) == "invalid"
    assert link_state(conn, used.token, now=NOW) == "used"
    assert link_state(conn, "unknown-token", now=NOW) == "invalid"
    assert link_state(conn, "", now=NOW) == "invalid"
    # used wins over expired
    assert link_state(conn, used.token, now=NOW + timedelta(days=30)) == "used"
    # the hash itself is not a token
    assert link_state(conn, _sha(pending.token), now=NOW) == "invalid"


def test_invite_state_and_list(conn: sqlite3.Connection) -> None:
    tokens = FakeTokenSource()
    a = _issue(conn, tokens, email="a@example.test")
    b = create_invite(
        conn,
        ADMIN_ID,
        email="b@example.test",
        is_admin=False,
        tokens=tokens,
        now=NOW + timedelta(minutes=1),
    )
    listed = list_invites(conn)
    assert [i.email for i in listed] == ["b@example.test", "a@example.test"]
    assert invite_state(a.invite, now=NOW) == "pending"
    assert invite_state(b.invite, now=NOW + timedelta(days=8)) == "expired"
    conn.execute(
        "UPDATE invites SET deleted_at = ? WHERE id = ?", ("2026-11-21T00:00:00.000Z", a.invite.id)
    )
    assert [i.email for i in list_invites(conn)] == ["b@example.test"]
    assert link_state(conn, a.token, now=NOW) == "invalid"


def test_token_and_hash_never_logged(
    conn: sqlite3.Connection, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    tokens = FakeTokenSource()
    first = _issue(conn, tokens)
    second = resend_invite(conn, ADMIN_ID, first.invite.id, tokens=tokens, now=NOW)
    link_state(conn, second.token, now=NOW)
    accept_invite(conn, second.token, name="n", password=PW, hasher=FAKE_HASHER, now=NOW)

    logged = caplog.text + "".join(str(r.__dict__) for r in caplog.records)
    for secret in (first.token, second.token, _sha(first.token), _sha(second.token)):
        assert secret not in logged
    assert second.token not in repr(second)
