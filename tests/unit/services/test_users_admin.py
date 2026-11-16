"""T-D17 — admin-panel user services (ADR-0061 §1/§4, ADR-0073)."""

from __future__ import annotations

import json
import sqlite3

import pytest

from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories import sessions as sessions_repo, users as users_repo
from budget_planner.services import _passwords
from budget_planner.services.users import (
    DUPLICATE_EMAIL_MESSAGE,
    INVALID_EMAIL_MESSAGE,
    LAST_ADMIN_DELETE_MESSAGE,
    LAST_ADMIN_DEMOTE_MESSAGE,
    NAME_MAX_LENGTH,
    SELF_DELETE_MESSAGE,
    UserConflict,
    UserDraft,
    UserInputError,
    UserNotFound,
    build_draft,
    create_user,
    edit_user,
    generate_password,
    get_live_user,
    list_live_users,
    reset_password,
    soft_delete_user,
)

ADMIN_ID = 1
CTX = RequestCtx(ip="127.0.0.1", user_id=ADMIN_ID, session_id="h", user_agent="pytest")


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_passwords, "DEFAULT_ROUNDS", 4)


@pytest.fixture
def admin_conn(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.execute(
        "UPDATE users SET email = 'root@example.test', is_admin = 1 WHERE id = ?", (ADMIN_ID,)
    )
    return conn


def _draft(email: str, *, admin: bool = False, name: str = "") -> UserDraft:
    return build_draft(email=email, name=name, is_admin=admin)


def _audit(conn: sqlite3.Connection, user_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM audit_log WHERE entity_type = 'users' AND entity_id = ? ORDER BY id",
        (user_id,),
    ).fetchall()


def _live_sessions(conn: sqlite3.Connection, user_id: int) -> int:
    row = conn.execute(
        "SELECT count(*) FROM sessions WHERE user_id = ? AND revoked_at IS NULL", (user_id,)
    ).fetchone()
    return int(row[0])


# --- pure helpers ---------------------------------------------------------


def test_generate_password_shape() -> None:
    first, second = generate_password(), generate_password()
    assert len(first) == 22
    assert first != second


@pytest.mark.parametrize(
    "email",
    ["", "nope", "@x.test", "a@", "a@b", "a b@x.test", "a@@x.test", "a@.", "x" * 250 + "@x.test"],
)
def test_build_draft_rejects_bad_email(email: str) -> None:
    with pytest.raises(UserInputError) as exc:
        build_draft(email=email, name="n", is_admin=False)
    assert exc.value.fields == {"email": INVALID_EMAIL_MESSAGE}


def test_build_draft_normalises() -> None:
    draft = build_draft(email="  Ann@Example.TEST ", name="  Ann   Lee ", is_admin=True)
    assert draft == UserDraft(email="ann@example.test", name="Ann Lee", is_admin=True)
    assert build_draft(email="bo@x.test", name="", is_admin=False).name == "bo"


def test_build_draft_rejects_long_name() -> None:
    with pytest.raises(UserInputError) as exc:
        build_draft(email="a@x.test", name="n" * (NAME_MAX_LENGTH + 1), is_admin=False)
    assert "name" in exc.value.fields


# --- create ---------------------------------------------------------------


def test_create_user_seeds_categories_and_hides_plaintext(admin_conn: sqlite3.Connection) -> None:
    user, password = create_user(admin_conn, ADMIN_ID, _draft("new@x.test"), request_ctx=CTX)
    assert user.must_change_password is True
    assert user.is_admin is False
    assert _passwords.verify_password(password, user.password_hash)
    cats = admin_conn.execute(
        "SELECT name, is_system FROM categories WHERE user_id = ? ORDER BY name", (user.id,)
    ).fetchall()
    assert [(c["name"], c["is_system"]) for c in cats] == [
        ("Reconciliation", 1),
        ("Transit", 1),
    ]
    rows = _audit(admin_conn, user.id)
    assert [r["operation"] for r in rows] == ["create"]
    assert rows[0]["actor_user_id"] == ADMIN_ID
    assert rows[0]["user_id"] == ADMIN_ID
    assert rows[0]["ip"] == "127.0.0.1"
    assert password not in "\n".join(admin_conn.iterdump())


def test_create_user_duplicate_email_case_insensitive(admin_conn: sqlite3.Connection) -> None:
    create_user(admin_conn, ADMIN_ID, _draft("dup@x.test"))
    with pytest.raises(UserInputError) as exc:
        create_user(admin_conn, ADMIN_ID, _draft("DUP@X.test"))
    assert exc.value.fields == {"email": DUPLICATE_EMAIL_MESSAGE}
    count = admin_conn.execute("SELECT count(*) FROM users").fetchone()[0]
    assert count == 2


def test_create_user_maps_integrity_race(
    admin_conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    create_user(admin_conn, ADMIN_ID, _draft("race@x.test"))
    # Simulate the uniqueness pre-check losing a race with a concurrent insert.
    monkeypatch.setattr(users_repo, "get_by_email_live", lambda _c, _e: None)
    with pytest.raises(UserInputError):
        create_user(admin_conn, ADMIN_ID, _draft("race@x.test"))


# --- list / get -----------------------------------------------------------


def test_list_live_users_excludes_deleted_and_reports_last_seen(
    admin_conn: sqlite3.Connection,
) -> None:
    alive, _ = create_user(admin_conn, ADMIN_ID, _draft("b@x.test"))
    gone, _ = create_user(admin_conn, ADMIN_ID, _draft("a@x.test"))
    soft_delete_user(admin_conn, ADMIN_ID, gone.id)
    sessions_repo.create_session(admin_conn, alive.id, ip=None, user_agent=None)
    listing = list_live_users(admin_conn)
    assert [u.email for u in listing] == ["b@x.test", "root@example.test"]
    by_id = {u.id: u for u in listing}
    assert by_id[alive.id].last_seen_at is not None
    assert by_id[ADMIN_ID].last_seen_at is None
    assert by_id[ADMIN_ID].is_admin is True


def test_get_live_user_missing(admin_conn: sqlite3.Connection) -> None:
    with pytest.raises(UserNotFound) as exc:
        get_live_user(admin_conn, 999)
    assert exc.value.user_id == 999


# --- edit -----------------------------------------------------------------


def test_edit_user_updates_and_audits(admin_conn: sqlite3.Connection) -> None:
    user, _ = create_user(admin_conn, ADMIN_ID, _draft("c@x.test"))
    updated = edit_user(
        admin_conn, ADMIN_ID, user.id, _draft("C2@x.test", admin=True, name="Cee"), request_ctx=CTX
    )
    assert (updated.email, updated.name, updated.is_admin) == ("c2@x.test", "Cee", True)
    update_row = _audit(admin_conn, user.id)[-1]
    assert update_row["operation"] == "update"
    assert update_row["actor_user_id"] == ADMIN_ID
    assert json.loads(update_row["prev_json"])["email"] == "c@x.test"


def test_edit_user_keeps_own_email(admin_conn: sqlite3.Connection) -> None:
    updated = edit_user(admin_conn, ADMIN_ID, ADMIN_ID, _draft("ROOT@example.test", admin=True))
    assert updated.email == "root@example.test"


def test_edit_user_duplicate_email(admin_conn: sqlite3.Connection) -> None:
    user, _ = create_user(admin_conn, ADMIN_ID, _draft("d@x.test"))
    with pytest.raises(UserInputError):
        edit_user(admin_conn, ADMIN_ID, user.id, _draft("Root@Example.test"))


def test_edit_user_refuses_demoting_last_admin(admin_conn: sqlite3.Connection) -> None:
    with pytest.raises(UserConflict) as exc:
        edit_user(admin_conn, ADMIN_ID, ADMIN_ID, _draft("root@example.test", admin=False))
    assert exc.value.message == LAST_ADMIN_DEMOTE_MESSAGE
    assert get_live_user(admin_conn, ADMIN_ID).is_admin is True
    assert _audit(admin_conn, ADMIN_ID) == []


def test_edit_user_allows_demote_with_second_admin(admin_conn: sqlite3.Connection) -> None:
    create_user(admin_conn, ADMIN_ID, _draft("e@x.test", admin=True))
    demoted = edit_user(admin_conn, ADMIN_ID, ADMIN_ID, _draft("root@example.test"))
    assert demoted.is_admin is False


def test_edit_user_missing(admin_conn: sqlite3.Connection) -> None:
    with pytest.raises(UserNotFound):
        edit_user(admin_conn, ADMIN_ID, 999, _draft("z@x.test"))


# --- reset password -------------------------------------------------------


def test_reset_password_regenerates_and_revokes(admin_conn: sqlite3.Connection) -> None:
    user, first = create_user(admin_conn, ADMIN_ID, _draft("f@x.test"))
    admin_conn.execute("UPDATE users SET must_change_password = 0 WHERE id = ?", (user.id,))
    sessions_repo.create_session(admin_conn, user.id, ip=None, user_agent=None)
    updated, second = reset_password(admin_conn, ADMIN_ID, user.id, request_ctx=CTX)
    assert second != first
    assert updated.must_change_password is True
    assert _passwords.verify_password(second, updated.password_hash)
    assert not _passwords.verify_password(first, updated.password_hash)
    assert _live_sessions(admin_conn, user.id) == 0
    last = _audit(admin_conn, user.id)[-1]
    new_json = json.loads(last["new_json"])
    assert (last["operation"], new_json["action"], new_json["sessions_revoked"]) == (
        "update",
        "reset_password",
        1,
    )
    assert last["actor_user_id"] == ADMIN_ID
    assert second not in "\n".join(admin_conn.iterdump())


def test_reset_password_missing(admin_conn: sqlite3.Connection) -> None:
    with pytest.raises(UserNotFound):
        reset_password(admin_conn, ADMIN_ID, 999)


def test_reset_password_target_deleted_mid_flight(
    admin_conn: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    user, _ = create_user(admin_conn, ADMIN_ID, _draft("g@x.test"))
    real_hash = _passwords.hash_password

    def _hash_then_delete(plain: str, *, rounds: int | None = None) -> str:
        admin_conn.execute("UPDATE users SET deleted_at = 'x' WHERE id = ?", (user.id,))
        return real_hash(plain, rounds=rounds)

    monkeypatch.setattr(_passwords, "hash_password", _hash_then_delete)
    with pytest.raises(UserNotFound):
        reset_password(admin_conn, ADMIN_ID, user.id)


# --- soft delete ----------------------------------------------------------


def test_soft_delete_revokes_sessions_and_audits(admin_conn: sqlite3.Connection) -> None:
    user, _ = create_user(admin_conn, ADMIN_ID, _draft("h@x.test"))
    sessions_repo.create_session(admin_conn, user.id, ip=None, user_agent=None)
    removed = soft_delete_user(admin_conn, ADMIN_ID, user.id, request_ctx=CTX)
    assert removed.id == user.id
    assert _live_sessions(admin_conn, user.id) == 0
    with pytest.raises(UserNotFound):
        get_live_user(admin_conn, user.id)
    last = _audit(admin_conn, user.id)[-1]
    assert (last["operation"], last["new_json"], last["actor_user_id"]) == (
        "delete",
        None,
        ADMIN_ID,
    )


def test_soft_delete_refuses_self(admin_conn: sqlite3.Connection) -> None:
    create_user(admin_conn, ADMIN_ID, _draft("i@x.test", admin=True))
    with pytest.raises(UserConflict) as exc:
        soft_delete_user(admin_conn, ADMIN_ID, ADMIN_ID)
    assert exc.value.message == SELF_DELETE_MESSAGE


def test_soft_delete_refuses_last_admin(admin_conn: sqlite3.Connection) -> None:
    # A non-admin actor (e.g. a session demoted mid-request) targets the sole admin.
    member, _ = create_user(admin_conn, ADMIN_ID, _draft("j@x.test"))
    sessions_repo.create_session(admin_conn, ADMIN_ID, ip=None, user_agent=None)
    with pytest.raises(UserConflict) as exc:
        soft_delete_user(admin_conn, member.id, ADMIN_ID)
    assert exc.value.message == LAST_ADMIN_DELETE_MESSAGE
    assert _live_sessions(admin_conn, ADMIN_ID) == 1
    assert get_live_user(admin_conn, ADMIN_ID).is_admin is True


def test_soft_delete_missing(admin_conn: sqlite3.Connection) -> None:
    with pytest.raises(UserNotFound):
        soft_delete_user(admin_conn, ADMIN_ID, 999)


def test_count_live_admins(admin_conn: sqlite3.Connection) -> None:
    assert users_repo.count_live_admins(admin_conn) == 1
    other, _ = create_user(admin_conn, ADMIN_ID, _draft("k@x.test", admin=True))
    assert users_repo.count_live_admins(admin_conn) == 2
    soft_delete_user(admin_conn, ADMIN_ID, other.id)
    assert users_repo.count_live_admins(admin_conn) == 1
