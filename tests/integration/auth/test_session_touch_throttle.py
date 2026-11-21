"""T-Q205 / Q-034: ``touch_session`` skips the write inside the throttle window."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from budget_planner.repositories import sessions as repo

pytestmark = pytest.mark.integration

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
LIFETIME_DAYS = 2


def _issue(conn: sqlite3.Connection, make_user: Callable[..., int]) -> str:
    return repo.create_session(
        conn, make_user(), ip=None, user_agent=None, lifetime_days=LIFETIME_DAYS, now=T0
    ).token


def _stored(conn: sqlite3.Connection, token: str, now: datetime) -> repo.Session:
    session = repo.get_session(conn, token, now=now)
    assert session is not None
    return session


def test_touch_inside_window_skips_write(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    token = _issue(conn, make_user)
    soon = T0 + repo.LAST_SEEN_THROTTLE - timedelta(seconds=1)

    expires = repo.touch_session(conn, token, lifetime_days=LIFETIME_DAYS, now=soon)

    stored = _stored(conn, token, soon)
    assert stored.last_seen_at == T0
    assert stored.expires_at == T0 + timedelta(days=LIFETIME_DAYS)
    assert expires == stored.expires_at


def test_touch_at_window_edge_writes(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    token = _issue(conn, make_user)
    edge = T0 + repo.LAST_SEEN_THROTTLE

    expires = repo.touch_session(conn, token, lifetime_days=LIFETIME_DAYS, now=edge)

    stored = _stored(conn, token, edge)
    assert stored.last_seen_at == edge
    assert expires == edge + timedelta(days=LIFETIME_DAYS)
    assert stored.expires_at == expires


def test_throttled_touch_still_rejects_revoked_session(
    conn: sqlite3.Connection, make_user: Callable[..., int]
) -> None:
    token = _issue(conn, make_user)
    repo.revoke_session(conn, token, now=T0)
    assert repo.touch_session(conn, token, now=T0 + timedelta(seconds=1)) is None
