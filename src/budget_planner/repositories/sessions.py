"""Server-side session store (ADR-0033 §3, ADR-0067 §2, ADR-0076).

The cookie carries a *token* (``secrets.token_urlsafe(32)``); ``sessions.id``
stores ``sha256(token)`` as lowercase hex, so a leaked DB file or backup
holds no usable bearer secret. Every lookup takes the token and hashes it
internally. Lifetime is sliding (:func:`touch_session` pushes ``expires_at``
forward by ``session_lifetime_days``) but clamped to
``created_at + session_absolute_lifetime_days``. :func:`get_session` only
returns live sessions — not revoked, not expired, owned by a non-deleted user.

Session rows are not audited here: the auth service writes one audit row
per login / logout / revoke event (ADR-0067 §4). ``touch_session`` runs on
every authenticated request and is deliberately un-audited.

Use :func:`session_handle` (``sha256(token)[:16]``, equal to
``Session.handle``) whenever a session must be referenced in logs or
``audit_log``.
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
_COLUMNS = (
    "id, user_id, created_at, last_seen_at, expires_at, revoked_at, user_agent, ip, "
    "authenticated_at"
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Session:
    """One row of ``sessions``. ``id`` is ``sha256(token)`` hex, never the token."""

    id: str
    user_id: int
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    user_agent: str | None
    ip: str | None
    authenticated_at: datetime

    @property
    def handle(self) -> str:
        """Non-secret identifier safe for logs / audit rows (``== session_handle(token)``)."""
        return self.id[:_HANDLE_HEX_CHARS]


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """A freshly created session plus the raw cookie token (shown only once)."""

    session: Session
    token: str


def hash_token(token: str) -> str:
    """Return the at-rest session id for cookie ``token`` (sha256 lowercase hex)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session_handle(token: str) -> str:
    """Return a short sha256-derived handle for ``token`` (ADR-0067 §4)."""
    return hash_token(token)[:_HANDLE_HEX_CHARS]


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _now(now: datetime | None) -> datetime:
    return datetime.now(UTC) if now is None else now


def _lifetime(lifetime_days: int | None) -> timedelta:
    days = get_settings().session_lifetime_days if lifetime_days is None else lifetime_days
    return timedelta(days=days)


def _absolute(absolute_days: int | None) -> timedelta:
    days = get_settings().session_absolute_lifetime_days if absolute_days is None else absolute_days
    return timedelta(days=days)


def _hydrate(row: sqlite3.Row) -> Session:
    created_at = parse_dt_required(row["created_at"])
    authenticated = parse_dt(row["authenticated_at"])
    return Session(
        id=row["id"],
        user_id=row["user_id"],
        created_at=created_at,
        last_seen_at=parse_dt_required(row["last_seen_at"]),
        expires_at=parse_dt_required(row["expires_at"]),
        revoked_at=parse_dt(row["revoked_at"]),
        user_agent=row["user_agent"],
        ip=row["ip"],
        authenticated_at=created_at if authenticated is None else authenticated,
    )


def create_session(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    ip: str | None,
    user_agent: str | None,
    lifetime_days: int | None = None,
    absolute_days: int | None = None,
    now: datetime | None = None,
) -> IssuedSession:
    """Insert a fresh session for ``user_id``; return it with its raw token."""
    current = _now(now)
    token = secrets.token_urlsafe(SESSION_ID_BYTES)
    session = Session(
        id=hash_token(token),
        user_id=user_id,
        created_at=current,
        last_seen_at=current,
        expires_at=min(current + _lifetime(lifetime_days), current + _absolute(absolute_days)),
        revoked_at=None,
        user_agent=user_agent,
        ip=ip,
        authenticated_at=current,
    )
    with transaction(conn):
        conn.execute(
            f"INSERT INTO sessions ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?)",
            (
                session.id,
                session.user_id,
                _iso(session.created_at),
                _iso(session.last_seen_at),
                _iso(session.expires_at),
                session.user_agent,
                session.ip,
                _iso(session.authenticated_at),
            ),
        )
    return IssuedSession(session=session, token=token)


def get_session(
    conn: sqlite3.Connection, token: str, *, now: datetime | None = None
) -> Session | None:
    """Return the live session for cookie ``token``; ``None`` if revoked/expired/unknown."""
    if not token:
        return None
    row = conn.execute(
        "SELECT s.id, s.user_id, s.created_at, s.last_seen_at, s.expires_at, "
        "s.revoked_at, s.user_agent, s.ip, s.authenticated_at "
        "FROM sessions s JOIN users u ON u.id = s.user_id "
        "WHERE s.id = ? AND s.revoked_at IS NULL AND s.expires_at > ? "
        "AND u.deleted_at IS NULL",
        (hash_token(token), _iso(_now(now))),
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


def revoke_session_by_id(
    conn: sqlite3.Connection, session_id: str, *, now: datetime | None = None
) -> bool:
    """Revoke by stored id (``sha256(token)``). ``True`` iff a live row changed."""
    with transaction(conn):
        cur = conn.execute(
            "UPDATE sessions SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
            (_iso(_now(now)), session_id),
        )
    return cur.rowcount > 0


def revoke_session(conn: sqlite3.Connection, token: str, *, now: datetime | None = None) -> bool:
    """Mark the session for cookie ``token`` revoked. ``True`` iff a live row changed."""
    return revoke_session_by_id(conn, hash_token(token), now=now)


def revoke_all_user_sessions(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    except_token: str | None = None,
    now: datetime | None = None,
) -> int:
    """Revoke every un-revoked session of ``user_id`` (optionally sparing one token).

    Returns the number of sessions revoked.
    """
    spared = None if except_token is None else hash_token(except_token)
    with transaction(conn):
        cur = conn.execute(
            "UPDATE sessions SET revoked_at = ? "
            "WHERE user_id = ? AND revoked_at IS NULL AND id IS NOT ?",
            (_iso(_now(now)), user_id, spared),
        )
    return cur.rowcount


def touch_session(
    conn: sqlite3.Connection,
    token: str,
    *,
    lifetime_days: int | None = None,
    absolute_days: int | None = None,
    now: datetime | None = None,
) -> datetime | None:
    """Slide a live session's expiry forward and bump ``last_seen_at``.

    The new expiry is ``min(now + lifetime, created_at + absolute lifetime)``
    (ADR-0076 §1) and is returned. ``None`` (nothing changed) when the
    session is revoked, expired, or unknown.
    """
    current = _now(now)
    key = hash_token(token)
    with transaction(conn):
        row = conn.execute(
            "SELECT created_at FROM sessions "
            "WHERE id = ? AND revoked_at IS NULL AND expires_at > ?",
            (key, _iso(current)),
        ).fetchone()
        if row is None:
            return None
        created_at = parse_dt_required(row["created_at"])
        expires_at = min(current + _lifetime(lifetime_days), created_at + _absolute(absolute_days))
        conn.execute(
            "UPDATE sessions SET last_seen_at = ?, expires_at = ? WHERE id = ?",
            (_iso(current), _iso(expires_at), key),
        )
    return expires_at


def mark_authenticated(
    conn: sqlite3.Connection, token: str, *, now: datetime | None = None
) -> bool:
    """Record that the holder just proved a credential (``authenticated_at = now``)."""
    with transaction(conn):
        cur = conn.execute(
            "UPDATE sessions SET authenticated_at = ? WHERE id = ? AND revoked_at IS NULL",
            (_iso(_now(now)), hash_token(token)),
        )
    return cur.rowcount > 0


def rotate_session_token(conn: sqlite3.Connection, token: str) -> IssuedSession | None:
    """Swap the token of a live session in place, keeping ``created_at`` (ADR-0076 §4).

    The old token stops resolving at once. ``None`` when ``token`` is not live.
    """
    new_token = secrets.token_urlsafe(SESSION_ID_BYTES)
    new_id = hash_token(new_token)
    with transaction(conn):
        cur = conn.execute(
            "UPDATE sessions SET id = ? WHERE id = ? AND revoked_at IS NULL",
            (new_id, hash_token(token)),
        )
        if cur.rowcount == 0:
            return None
        row = conn.execute(f"SELECT {_COLUMNS} FROM sessions WHERE id = ?", (new_id,)).fetchone()
    return IssuedSession(session=_hydrate(row), token=new_token)


__all__ = [
    "IssuedSession",
    "Session",
    "create_session",
    "get_session",
    "hash_token",
    "list_active_sessions",
    "mark_authenticated",
    "revoke_all_user_sessions",
    "revoke_session",
    "revoke_session_by_id",
    "rotate_session_token",
    "session_handle",
    "touch_session",
]
