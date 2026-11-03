"""T-D18 — self-service password change service (ADR-0061 §4, ADR-0074)."""

from __future__ import annotations

import json
import sqlite3

import pytest

from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories import sessions as sessions_repo
from budget_planner.repositories.users import UserNotFoundError
from budget_planner.services import _passwords, password_change as svc
from budget_planner.services.password_change import (
    PasswordChangeOutcome,
    PasswordChangeRequest,
    change_own_password,
    validate_new_password,
)
from tests.auth_support import TEST_PASSWORD, issue_session, seed_login_user

NEW_PASSWORD = "a-brand-new-passphrase"  # noqa: S105  # pragma: allowlist secret
CTX = RequestCtx(ip="203.0.113.7", user_id=1, session_id="h4ndle", user_agent="pytest-ua")


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_passwords, "DEFAULT_ROUNDS", 4)


@pytest.fixture
def user_id(conn: sqlite3.Connection) -> int:
    uid = seed_login_user(conn)
    conn.execute("UPDATE users SET must_change_password = 1 WHERE id = ?", (uid,))
    return uid


def _req(
    current: str = TEST_PASSWORD, new: str = NEW_PASSWORD, confirm: str | None = None
) -> PasswordChangeRequest:
    return PasswordChangeRequest(
        current_password=current,
        new_password=new,
        confirm_password=new if confirm is None else confirm,
    )


def _user_row(conn: sqlite3.Connection, uid: int) -> sqlite3.Row:
    row: sqlite3.Row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return row


def _audit(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM audit_log ORDER BY id").fetchall()


def _fields(outcome: PasswordChangeOutcome) -> set[str]:
    return {e.field for e in outcome.errors}


# --- policy (pure) ----------------------------------------------------------


def test_validate_accepts_good_password() -> None:
    assert validate_new_password(_req()) == ()


@pytest.mark.parametrize(
    ("new", "confirm", "field", "message"),
    [
        ("short", None, "new_password", svc.MSG_TOO_SHORT),
        ("x" * 73, None, "new_password", svc.MSG_TOO_LONG),
        ("ż" * 37, None, "new_password", svc.MSG_TOO_LONG),  # 74 bytes, 37 chars
        (TEST_PASSWORD, None, "new_password", svc.MSG_SAME_AS_CURRENT),
        (NEW_PASSWORD, "different-confirm-pw", "confirm_password", svc.MSG_MISMATCH),
    ],
)
def test_validate_rejects(new: str, confirm: str | None, field: str, message: str) -> None:
    errors = validate_new_password(_req(new=new, confirm=confirm))
    assert any(e.field == field and e.message == message for e in errors)


def test_validate_accepts_exactly_72_bytes() -> None:
    assert validate_new_password(_req(new="x" * 72)) == ()


def test_outcome_message_for() -> None:
    outcome = PasswordChangeOutcome(errors=(svc.FieldError(field="new_password", message="boom"),))
    assert not outcome.ok
    assert outcome.message_for("new_password") == "boom"
    assert outcome.message_for("confirm_password") is None


def test_request_repr_redacts_plaintext() -> None:
    assert TEST_PASSWORD not in repr(_req())
    assert NEW_PASSWORD not in repr(_req())


# --- change_own_password ----------------------------------------------------


def test_change_own_password_happy_path(conn: sqlite3.Connection, user_id: int) -> None:
    current = issue_session(conn, user_id=user_id)
    other_a = issue_session(conn, user_id=user_id)
    other_b = issue_session(conn, user_id=user_id)
    foreign_user = seed_login_user(conn, user_id=2, email="someone@example.test")
    foreign = issue_session(conn, user_id=foreign_user)

    outcome = change_own_password(
        conn, user_id, _req(), current_session_id=current, request_ctx=CTX
    )

    assert outcome.ok
    assert outcome.revoked_sessions == 2
    row = _user_row(conn, user_id)
    assert row["must_change_password"] == 0
    assert _passwords.verify_password(NEW_PASSWORD, row["password_hash"])
    assert not _passwords.verify_password(TEST_PASSWORD, row["password_hash"])
    assert sessions_repo.get_session(conn, current) is not None
    assert sessions_repo.get_session(conn, other_a) is None
    assert sessions_repo.get_session(conn, other_b) is None
    assert sessions_repo.get_session(conn, foreign) is not None


def test_change_own_password_audits_without_secrets(conn: sqlite3.Connection, user_id: int) -> None:
    current = issue_session(conn, user_id=user_id)
    issue_session(conn, user_id=user_id)
    change_own_password(conn, user_id, _req(), current_session_id=current, request_ctx=CTX)

    rows = _audit(conn)
    users_rows = [r for r in rows if r["entity_type"] == "users"]
    session_rows = [r for r in rows if r["entity_type"] == "session"]
    assert len(users_rows) == 1
    assert users_rows[0]["operation"] == "update"
    new = json.loads(users_rows[0]["new_json"])
    assert new["password_changed"] is True
    assert new["must_change_password"] is False
    assert len(session_rows) == 1
    assert json.loads(session_rows[0]["prev_json"]) == {
        "event": "password_change_revoke_others",
        "count": 1,
    }
    hashed = _user_row(conn, user_id)["password_hash"]
    for r in rows:
        assert r["ip"] == "203.0.113.7"
        assert r["user_agent"] == "pytest-ua"
        blob = f"{r['prev_json']}{r['new_json']}"
        assert TEST_PASSWORD not in blob
        assert NEW_PASSWORD not in blob
        assert hashed not in blob


def test_change_own_password_no_other_sessions_skips_revoke_audit(
    conn: sqlite3.Connection, user_id: int
) -> None:
    current = issue_session(conn, user_id=user_id)
    outcome = change_own_password(
        conn, user_id, _req(), current_session_id=current, request_ctx=CTX
    )
    assert outcome.ok
    assert outcome.revoked_sessions == 0
    assert not [r for r in _audit(conn) if r["entity_type"] == "session"]


def test_change_own_password_wrong_current(conn: sqlite3.Connection, user_id: int) -> None:
    before = _user_row(conn, user_id)["password_hash"]
    other = issue_session(conn, user_id=user_id)

    outcome = change_own_password(
        conn,
        user_id,
        _req(current="not-my-password"),
        current_session_id=None,
        request_ctx=CTX,
    )

    assert _fields(outcome) == {"current_password"}
    assert outcome.message_for("current_password") == svc.MSG_CURRENT_WRONG
    row = _user_row(conn, user_id)
    assert row["password_hash"] == before
    assert row["must_change_password"] == 1
    assert sessions_repo.get_session(conn, other) is not None
    rows = _audit(conn)
    assert len(rows) == 1
    assert rows[0]["entity_type"] == "auth_event"
    assert rows[0]["entity_id"] == user_id
    assert rows[0]["operation"] == "create"
    assert rows[0]["user_id"] == user_id
    assert rows[0]["ip"] == "203.0.113.7"
    assert rows[0]["user_agent"] == "pytest-ua"
    assert json.loads(rows[0]["new_json"]) == {
        "event": "password_change_failed",
        "reason": "bad_current_password",
    }
    assert "not-my-password" not in rows[0]["new_json"]


def test_change_own_password_wrong_current_also_reports_policy(
    conn: sqlite3.Connection, user_id: int
) -> None:
    outcome = change_own_password(
        conn,
        user_id,
        _req(current="nope-nope-nope", new="short"),
        current_session_id=None,
        request_ctx=CTX,
    )
    assert _fields(outcome) == {"current_password", "new_password"}


def test_change_own_password_no_password_hash(conn: sqlite3.Connection, user_id: int) -> None:
    conn.execute("UPDATE users SET password_hash = NULL WHERE id = ?", (user_id,))
    outcome = change_own_password(conn, user_id, _req(), current_session_id=None, request_ctx=CTX)
    assert _fields(outcome) == {"current_password"}
    assert json.loads(_audit(conn)[0]["new_json"])["reason"] == "no_password"


def test_change_own_password_missing_current_is_not_audited(
    conn: sqlite3.Connection, user_id: int
) -> None:
    outcome = change_own_password(
        conn, user_id, _req(current=""), current_session_id=None, request_ctx=CTX
    )
    assert outcome.message_for("current_password") == svc.MSG_CURRENT_REQUIRED
    assert _audit(conn) == []


@pytest.mark.parametrize(
    ("new", "confirm", "field"),
    [
        ("too-short", None, "new_password"),
        ("y" * 80, None, "new_password"),
        (TEST_PASSWORD, None, "new_password"),
        (NEW_PASSWORD, "nope-not-the-same", "confirm_password"),
    ],
)
def test_change_own_password_policy_failure_no_mutation(
    conn: sqlite3.Connection, user_id: int, new: str, confirm: str | None, field: str
) -> None:
    before = _user_row(conn, user_id)["password_hash"]
    outcome = change_own_password(
        conn, user_id, _req(new=new, confirm=confirm), current_session_id=None, request_ctx=CTX
    )
    assert field in _fields(outcome)
    assert "current_password" not in _fields(outcome)
    assert _user_row(conn, user_id)["password_hash"] == before
    assert _audit(conn) == []


def test_change_own_password_stale_hash_rejected(
    conn: sqlite3.Connection, user_id: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_hash = _passwords.hash_password

    def _hash_then_race(plain: str, *, rounds: int | None = None) -> str:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (real_hash("someone-else-won", rounds=4), user_id),
        )
        return real_hash(plain, rounds=rounds)

    monkeypatch.setattr(_passwords, "hash_password", _hash_then_race)
    outcome = change_own_password(conn, user_id, _req(), current_session_id=None, request_ctx=CTX)
    assert outcome.message_for("current_password") == svc.MSG_STALE
    assert _user_row(conn, user_id)["must_change_password"] == 1


def test_change_own_password_unknown_user(conn: sqlite3.Connection) -> None:
    with pytest.raises(UserNotFoundError):
        change_own_password(conn, 999, _req(), current_session_id=None, request_ctx=CTX)
