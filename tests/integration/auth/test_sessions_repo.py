"""Integration tests for ``repositories.sessions`` (T-D02a, ADR-0067 §2)."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from budget_planner.repositories import sessions as repo

pytestmark = pytest.mark.integration

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def test_create_session_uses_random_urlsafe_id_and_settings_lifetime(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    s = repo.create_session(conn, uid, ip="203.0.113.5", user_agent="ua/1", now=T0)

    assert len(s.id) >= 43
    assert s.expires_at == T0 + timedelta(days=14)  # settings default
    assert s.revoked_at is None
    assert repo.create_session(conn, uid, ip=None, user_agent=None).id != s.id

    fetched = repo.get_session(conn, s.id, now=T0)
    assert fetched == s


def test_get_session_none_for_unknown_or_empty(conn: sqlite3.Connection) -> None:
    assert repo.get_session(conn, "nope") is None
    assert repo.get_session(conn, "") is None


def test_get_session_none_when_expired(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    s = repo.create_session(conn, uid, ip=None, user_agent=None, lifetime_days=1, now=T0)
    assert repo.get_session(conn, s.id, now=T0 + timedelta(hours=23)) is not None
    assert repo.get_session(conn, s.id, now=T0 + timedelta(days=1)) is None


def test_get_session_none_when_revoked(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    s = repo.create_session(conn, uid, ip=None, user_agent=None)
    assert repo.revoke_session(conn, s.id) is True
    assert repo.get_session(conn, s.id) is None
    assert repo.revoke_session(conn, s.id) is False


def test_get_session_none_when_user_soft_deleted(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    s = repo.create_session(conn, uid, ip=None, user_agent=None)
    conn.execute("UPDATE users SET deleted_at = '2026-01-01T00:00:00Z' WHERE id = ?", (uid,))
    assert repo.get_session(conn, s.id) is None


def test_revoke_all_user_sessions_spares_current_and_other_users(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    alice = make_user()
    bob = make_user(email="bob@example.test", name="Bob")
    current = repo.create_session(conn, alice, ip=None, user_agent=None)
    other_a = repo.create_session(conn, alice, ip=None, user_agent=None)
    other_b = repo.create_session(conn, alice, ip=None, user_agent=None)
    bobs = repo.create_session(conn, bob, ip=None, user_agent=None)

    revoked = repo.revoke_all_user_sessions(conn, alice, except_session_id=current.id)

    assert revoked == 2
    assert repo.get_session(conn, current.id) is not None
    assert repo.get_session(conn, other_a.id) is None
    assert repo.get_session(conn, other_b.id) is None
    assert repo.get_session(conn, bobs.id) is not None


def test_revoke_all_user_sessions_without_exception_revokes_everything(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    a = repo.create_session(conn, uid, ip=None, user_agent=None)
    repo.create_session(conn, uid, ip=None, user_agent=None)
    assert repo.revoke_all_user_sessions(conn, uid) == 2
    assert repo.get_session(conn, a.id) is None
    assert repo.list_active_sessions(conn, uid) == ()


def test_touch_session_slides_expiry_and_bumps_last_seen(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    s = repo.create_session(conn, uid, ip=None, user_agent=None, lifetime_days=2, now=T0)
    later = T0 + timedelta(days=1)

    assert repo.touch_session(conn, s.id, lifetime_days=2, now=later) is True

    touched = repo.get_session(conn, s.id, now=later)
    assert touched is not None
    assert touched.last_seen_at == later
    assert touched.expires_at == later + timedelta(days=2)
    # Still alive past the original expiry thanks to the slide.
    assert repo.get_session(conn, s.id, now=T0 + timedelta(days=2, hours=1)) is not None


def test_touch_session_noop_on_expired_or_revoked(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    s = repo.create_session(conn, uid, ip=None, user_agent=None, lifetime_days=1, now=T0)
    assert repo.touch_session(conn, s.id, now=T0 + timedelta(days=2)) is False

    r = repo.create_session(conn, uid, ip=None, user_agent=None)
    repo.revoke_session(conn, r.id)
    assert repo.touch_session(conn, r.id) is False


def test_list_active_sessions_orders_by_last_seen(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    uid = make_user()
    older = repo.create_session(conn, uid, ip=None, user_agent="old", now=T0)
    newer = repo.create_session(conn, uid, ip=None, user_agent="new", now=T0)
    repo.touch_session(conn, newer.id, now=T0 + timedelta(minutes=5))

    listed = repo.list_active_sessions(conn, uid, now=T0 + timedelta(minutes=6))
    assert [s.id for s in listed] == [newer.id, older.id]


def test_session_handle_is_stable_and_not_the_id() -> None:
    sid = "abc"
    assert repo.session_handle(sid) == repo.session_handle(sid)
    assert len(repo.session_handle(sid)) == 16
    assert repo.session_handle(sid) != sid
