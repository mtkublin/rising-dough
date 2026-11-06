"""Integration tests for ``repositories.sessions`` (T-D02a, T-D53a; ADR-0067 §2, ADR-0076)."""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from budget_planner.config import Settings
from budget_planner.repositories import sessions as repo

pytestmark = pytest.mark.integration

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def test_create_session_hashes_token_and_uses_settings_lifetime(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    issued = repo.create_session(conn, uid, ip="203.0.113.5", user_agent="ua/1", now=T0)
    s = issued.session

    assert len(issued.token) >= 43
    assert s.id == hashlib.sha256(issued.token.encode()).hexdigest()
    assert s.id != issued.token
    assert s.expires_at == T0 + timedelta(days=14)  # settings default
    assert s.authenticated_at == T0
    assert s.revoked_at is None
    assert repo.create_session(conn, uid, ip=None, user_agent=None).token != issued.token

    assert repo.get_session(conn, issued.token, now=T0) == s
    assert repo.get_session(conn, s.id, now=T0) is None  # the hash is not a credential


def test_db_never_contains_raw_token(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    issued = repo.create_session(conn, uid, ip=None, user_agent=None)
    repo.touch_session(conn, issued.token)
    dump = "\n".join(conn.iterdump())
    assert issued.token not in dump
    ids = [r["id"] for r in conn.execute("SELECT id FROM sessions")]
    assert ids == [hashlib.sha256(issued.token.encode()).hexdigest()]


def test_handle_agrees_with_session_handle(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    issued = repo.create_session(conn, make_user(), ip=None, user_agent=None)
    assert issued.session.handle == repo.session_handle(issued.token)


def test_get_session_none_for_unknown_or_empty(conn: sqlite3.Connection) -> None:
    assert repo.get_session(conn, "nope") is None
    assert repo.get_session(conn, "") is None


def test_get_session_none_when_expired(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    t = repo.create_session(conn, uid, ip=None, user_agent=None, lifetime_days=1, now=T0).token
    assert repo.get_session(conn, t, now=T0 + timedelta(hours=23)) is not None
    assert repo.get_session(conn, t, now=T0 + timedelta(days=1)) is None


def test_get_session_none_when_revoked(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    t = repo.create_session(conn, uid, ip=None, user_agent=None).token
    assert repo.revoke_session(conn, t) is True
    assert repo.get_session(conn, t) is None
    assert repo.revoke_session(conn, t) is False


def test_get_session_none_when_user_soft_deleted(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    t = repo.create_session(conn, uid, ip=None, user_agent=None).token
    conn.execute("UPDATE users SET deleted_at = '2026-01-01T00:00:00Z' WHERE id = ?", (uid,))
    assert repo.get_session(conn, t) is None


def test_revoke_all_user_sessions_spares_current_and_other_users(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    alice = make_user()
    bob = make_user(email="bob@example.test", name="Bob")
    current = repo.create_session(conn, alice, ip=None, user_agent=None).token
    other_a = repo.create_session(conn, alice, ip=None, user_agent=None).token
    other_b = repo.create_session(conn, alice, ip=None, user_agent=None).token
    bobs = repo.create_session(conn, bob, ip=None, user_agent=None).token

    revoked = repo.revoke_all_user_sessions(conn, alice, except_token=current)

    assert revoked == 2
    assert repo.get_session(conn, current) is not None
    assert repo.get_session(conn, other_a) is None
    assert repo.get_session(conn, other_b) is None
    assert repo.get_session(conn, bobs) is not None


def test_revoke_all_user_sessions_without_exception_revokes_everything(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    a = repo.create_session(conn, uid, ip=None, user_agent=None).token
    repo.create_session(conn, uid, ip=None, user_agent=None)
    assert repo.revoke_all_user_sessions(conn, uid) == 2
    assert repo.get_session(conn, a) is None
    assert repo.list_active_sessions(conn, uid) == ()


def test_touch_session_slides_expiry_and_bumps_last_seen(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    t = repo.create_session(conn, uid, ip=None, user_agent=None, lifetime_days=2, now=T0).token
    later = T0 + timedelta(days=1)

    assert repo.touch_session(conn, t, lifetime_days=2, now=later) == later + timedelta(days=2)

    touched = repo.get_session(conn, t, now=later)
    assert touched is not None
    assert touched.last_seen_at == later
    assert touched.expires_at == later + timedelta(days=2)
    # Still alive past the original expiry thanks to the slide.
    assert repo.get_session(conn, t, now=T0 + timedelta(days=2, hours=1)) is not None


def test_touch_session_noop_on_expired_or_revoked(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    s = repo.create_session(conn, uid, ip=None, user_agent=None, lifetime_days=1, now=T0).token
    assert repo.touch_session(conn, s, now=T0 + timedelta(days=2)) is None

    r = repo.create_session(conn, uid, ip=None, user_agent=None).token
    repo.revoke_session(conn, r)
    assert repo.touch_session(conn, r) is None


def test_touch_session_never_extends_past_absolute_cap(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    """Continuous daily activity cannot keep a session alive beyond the cap."""
    uid = make_user()
    t = repo.create_session(
        conn, uid, ip=None, user_agent=None, lifetime_days=14, absolute_days=30, now=T0
    ).token
    cap = T0 + timedelta(days=30)

    for day in range(1, 30):
        now = T0 + timedelta(days=day)
        expires = repo.touch_session(conn, t, lifetime_days=14, absolute_days=30, now=now)
        assert expires is not None
        assert expires <= cap
    assert repo.get_session(conn, t, now=T0 + timedelta(days=29, hours=23)) is not None
    stored = repo.get_session(conn, t, now=T0 + timedelta(days=29))
    assert stored is not None
    assert stored.expires_at == cap

    assert repo.get_session(conn, t, now=cap) is None
    assert repo.touch_session(conn, t, lifetime_days=14, absolute_days=30, now=cap) is None


def test_create_session_expiry_is_clamped_to_absolute_cap(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    s = repo.create_session(
        conn, make_user(), ip=None, user_agent=None, lifetime_days=14, absolute_days=7, now=T0
    ).session
    assert s.expires_at == T0 + timedelta(days=7)


def test_rotate_session_token_keeps_created_at_and_kills_old_token(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    issued = repo.create_session(conn, uid, ip="1.2.3.4", user_agent="ua", now=T0)

    rotated = repo.rotate_session_token(conn, issued.token)

    assert rotated is not None
    assert rotated.token != issued.token
    assert rotated.session.id == repo.hash_token(rotated.token)
    assert rotated.session.created_at == T0
    assert rotated.session.expires_at == issued.session.expires_at
    assert repo.get_session(conn, issued.token, now=T0) is None
    assert repo.get_session(conn, rotated.token, now=T0) == rotated.session
    assert repo.rotate_session_token(conn, issued.token) is None  # old token is dead


def test_mark_authenticated_updates_timestamp(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    t = repo.create_session(conn, make_user(), ip=None, user_agent=None, now=T0).token
    later = T0 + timedelta(minutes=30)
    assert repo.mark_authenticated(conn, t, now=later) is True
    got = repo.get_session(conn, t, now=later)
    assert got is not None
    assert got.authenticated_at == later
    repo.revoke_session(conn, t)
    assert repo.mark_authenticated(conn, t) is False


def test_null_authenticated_at_reads_as_created_at(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    t = repo.create_session(conn, make_user(), ip=None, user_agent=None, now=T0).token
    conn.execute("UPDATE sessions SET authenticated_at = NULL")
    got = repo.get_session(conn, t, now=T0)
    assert got is not None
    assert got.authenticated_at == got.created_at == T0


def test_list_active_sessions_orders_by_last_seen(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    older = repo.create_session(conn, uid, ip=None, user_agent="old", now=T0)
    newer = repo.create_session(conn, uid, ip=None, user_agent="new", now=T0)
    repo.touch_session(conn, newer.token, now=T0 + timedelta(minutes=5))

    listed = repo.list_active_sessions(conn, uid, now=T0 + timedelta(minutes=6))
    assert [s.id for s in listed] == [newer.session.id, older.session.id]


def test_session_handle_is_stable_and_not_the_id() -> None:
    sid = "abc"
    assert repo.session_handle(sid) == repo.session_handle(sid)
    assert len(repo.session_handle(sid)) == 16
    assert repo.session_handle(sid) != sid


def test_settings_reject_absolute_lifetime_below_sliding() -> None:
    with pytest.raises(ValueError, match="session_absolute_lifetime_days"):
        Settings(session_lifetime_days=30, session_absolute_lifetime_days=14)
