"""Server-side session store (ADR-0033 §3, ADR-0067 §2).

The session id is ``secrets.token_urlsafe(32)`` and doubles as the cookie
value. Lifetime is sliding: :func:`touch_session` pushes ``expires_at``
forward by ``session_lifetime_days`` (settings) and updates
``last_seen_at``. :func:`get_session` only returns live sessions — not
revoked, not expired, and owned by a non-deleted user.

Session rows are not audited here: the auth service writes one audit row
per login / logout / revoke event (ADR-0067 §4). ``touch_session`` runs on
every authenticated request and is deliberately un-audited.

Raw session ids are bearer secrets; use :func:`session_handle` whenever a
session must be referenced in logs or ``audit_log``.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Final

from budget_planner.config import get_settings
from budget_planner.repositories._shared import parse_dt, parse_dt_required, transaction

SESSION_ID_BYTES: Final = 32
_HANDLE_HEX_CHARS: Final = 16
_COLUMNS = "id, user_id, created_at, last_seen_at, expires_at, revoked_at, user_agent, ip"


@dataclass(frozen=True, slots=True, kw_only=True)
class Session:
    """One row of ``sessions``."""

    id: str
    user_id: int
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    user_agent: str | None
    ip: str | None

    @property
    def handle(self) -> str:
        """Non-secret identifier safe for logs / audit rows."""
        return session_handle(self.id)


def session_handle(session_id: str) -> str:
    """Return a short sha256-derived handle for ``session_id`` (ADR-0067 §4)."""
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:_HANDLE_HEX_CHARS]


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _now(now: datetime | None) -> datetime:
    return datetime.now(UTC) if now is None else now


def _lifetime(lifetime_days: int | None) -> timedelta:
    days = get_settings().session_lifetime_days if lifetime_days is None else lifetime_days
    return timedelta(days=days)


def _hydrate(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"],
        user_id=row["user_id"],
        created_at=parse_dt_required(row["created_at"]),
        last_seen_at=parse_dt_required(row["last_seen_at"]),
        expires_at=parse_dt_required(row["expires_at"]),
        revoked_at=parse_dt(row["revoked_at"]),
        user_agent=row["user_agent"],
        ip=row["ip"],
    )


def create_session(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    ip: str | None,
    user_agent: str | None,
    lifetime_days: int | None = None,
    now: datetime | None = None,
) -> Session:
    """Insert and return a fresh session for ``user_id``."""
    current = _now(now)
    session = Session(
        id=secrets.token_urlsafe(SESSION_ID_BYTES),
        user_id=user_id,
        created_at=current,
        last_seen_at=current,
        expires_at=current + _lifetime(lifetime_days),
        revoked_at=None,
        user_agent=user_agent,
        ip=ip,
    )
    with transaction(conn):
        conn.execute(
            f"INSERT INTO sessions ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
            (
                session.id,
                session.user_id,
                _iso(session.created_at),
                _iso(session.last_seen_at),
                _iso(session.expires_at),
                session.user_agent,
                session.ip,
            ),
        )
    return session


def get_session(
    conn: sqlite3.Connection, session_id: str, *, now: datetime | None = None
) -> Session | None:
    """Return the live session for ``session_id``; ``None`` if revoked/expired/unknown."""
    if not session_id:
        return None
    row = conn.execute(
        "SELECT s.id, s.user_id, s.created_at, s.last_seen_at, s.expires_at, "
        "s.revoked_at, s.user_agent, s.ip "
        "FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.id = ? AND s.revoked_at IS NULL AND s.expires_at > ? "
        "AND u.deleted_at IS NULL",
        (session_id, _iso(_now(now))),
    ).fetchone()
    return None if row is None else _hydrate(row)


def list_active_sessions(
    conn: sqlite3.Connection, user_id: int, *, now: datetime | None = None
) -> tuple[Session, ...]:
    """Return ``user_id``'s live sessions, most recently seen first."""
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM sessions "
        "WHERE user_id = ? AND revoked_at IS NULL AND expires_at > ? "
        "ORDER BY last_seen_at DESC, created_at DESC",
        (user_id, _iso(_now(now))),
    ).fetchall()
    return tuple(_hydrate(r) for r in rows)


def revoke_session(
    conn: sqlite3.Connection, session_id: str, *, now: datetime | None = None
) -> bool:
    """Mark ``session_id`` revoked. Returns ``True`` iff a live row changed."""
    with transaction(conn):
        cur = conn.execute(
            "UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (_iso(_now(now)), session_id),
        )
    return cur.rowcount > 0


def revoke_all_user_sessions(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    except_session_id: str | None = None,
    now: datetime | None = None,
) -> int:
    """Revoke every un-revoked session of ``user_id`` (optionally sparing one).

    Returns the number of sessions revoked.
    """
    with transaction(conn):
        cur = conn.execute(
            "UPDATE sessions SET revoked_at = ? "
            "WHERE user_id = ? AND revoked_at IS NULL AND id IS NOT ?",
            (_iso(_now(now)), user_id, except_session_id),
        )
    return cur.rowcount


def touch_session(
    conn: sqlite3.Connection,
    session_id: str,
    *,
    lifetime_days: int | None = None,
    now: datetime | None = None,
) -> bool:
    """Slide a live session's expiry forward and bump ``last_seen_at``.

    Returns ``False`` (and changes nothing) when the session is revoked,
    expired, or unknown.
    """
    current = _now(now)
    with transaction(conn):
        cur = conn.execute(
            "UPDATE sessions SET last_seen_at = ?, expires_at = ? "
            "WHERE id = ? AND revoked_at IS NULL AND expires_at > ?",
            (
                _iso(current),
                _iso(current + _lifetime(lifetime_days)),
                session_id,
                _iso(current),
            ),
        )
    return cur.rowcount > 0


__all__ = [
    "Session",
    "create_session",
    "get_session",
    "list_active_sessions",
    "revoke_all_user_sessions",
    "revoke_session",
    "session_handle",
    "touch_session",
]
