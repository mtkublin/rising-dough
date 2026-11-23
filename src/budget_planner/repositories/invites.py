"""``invites`` repository (T-UR30, ADR-0134 section 1 and 10, ADR-0022).

An invite is admin-managed, app-wide data (not owned by the person it invites,
and the token lookup happens before any user is known), so functions take
``conn`` first and name the acting admin in ``invited_by`` / ``actor_user_id``,
like ``users`` and ``sessions``. Only ``sha256(token)`` is stored
(:func:`budget_planner.repositories.sessions.hash_token`); the token and its
hash never enter an audit payload.

Every mutation runs in one transaction with its ``audit_log`` row (operation ``create`` or
``update``, the only ones the audit CHECK allows; prev/new payloads show which timestamp moved).
Timestamps come in as arguments and are stored as UTC text via ``clock.iso_utc``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from budget_planner import clock
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories._shared import (
    parse_dt,
    parse_dt_required,
    transaction,
    write_audit,
)

_ENTITY = "invites"
_EMPTY_REQUEST_CTX: RequestCtx = RequestCtx.empty()
_COLUMNS = (
    "id, email, is_admin, invited_by, token_hash, created_at, updated_at, "
    "expires_at, used_at, revoked_at"
)


@dataclass(frozen=True, slots=True, kw_only=True)
class Invite:
    """One live ``invites`` row. ``token_hash`` is ``sha256(token)`` hex."""

    id: int
    email: str
    is_admin: bool
    invited_by: int
    token_hash: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    used_at: datetime | None
    revoked_at: datetime | None


def _hydrate(row: sqlite3.Row) -> Invite:
    return Invite(
        id=int(row["id"]),
        email=str(row["email"]),
        is_admin=bool(row["is_admin"]),
        invited_by=int(row["invited_by"]),
        token_hash=str(row["token_hash"]),
        created_at=parse_dt_required(row["created_at"]),
        updated_at=parse_dt_required(row["updated_at"]),
        expires_at=parse_dt_required(row["expires_at"]),
        used_at=parse_dt(row["used_at"]),
        revoked_at=parse_dt(row["revoked_at"]),
    )


def _audit_payload(invite: Invite) -> dict[str, object]:
    """Audit view of an invite: never the token hash (T-UR30)."""
    return {
        "id": invite.id,
        "email": invite.email,
        "is_admin": invite.is_admin,
        "invited_by": invite.invited_by,
        "created_at": clock.iso_utc(invite.created_at),
        "expires_at": clock.iso_utc(invite.expires_at),
        "used_at": None if invite.used_at is None else clock.iso_utc(invite.used_at),
        "revoked_at": None if invite.revoked_at is None else clock.iso_utc(invite.revoked_at),
    }


def get_live(conn: sqlite3.Connection, invite_id: int) -> Invite | None:
    """Return the live (not soft-deleted) invite, or ``None``."""
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM invites WHERE id = ? AND deleted_at IS NULL", (invite_id,)
    ).fetchone()
    return None if row is None else _hydrate(row)


def find_by_token_hash(conn: sqlite3.Connection, token_hash: str) -> Invite | None:
    """Return the live invite whose stored hash is ``token_hash``, or ``None``."""
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM invites WHERE token_hash = ? AND deleted_at IS NULL",
        (token_hash,),
    ).fetchone()
    return None if row is None else _hydrate(row)


def list_live(conn: sqlite3.Connection) -> list[Invite]:
    """Every live invite, newest first."""
    rows = conn.execute(
        f"SELECT {_COLUMNS} FROM invites WHERE deleted_at IS NULL ORDER BY created_at DESC, id DESC"
    ).fetchall()
    return [_hydrate(r) for r in rows]


def find_pending_for_email(conn: sqlite3.Connection, email: str, *, now: datetime) -> Invite | None:
    """Return a live invite for ``email`` that is not used, revoked or expired at ``now``."""
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM invites WHERE lower(email) = lower(?) AND deleted_at IS NULL "
        "AND used_at IS NULL AND revoked_at IS NULL AND expires_at > ? ORDER BY id LIMIT 1",
        (email, clock.iso_utc(now)),
    ).fetchone()
    return None if row is None else _hydrate(row)


def _require_live_invite(conn: sqlite3.Connection, invite_id: int) -> Invite:
    invite = get_live(conn, invite_id)
    if invite is None:
        raise LookupError(f"no live invite with id {invite_id}")
    return invite


def insert(
    conn: sqlite3.Connection,
    *,
    email: str,
    is_admin: bool,
    invited_by: int,
    token_hash: str,
    created_at: datetime,
    expires_at: datetime,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> Invite:
    """Insert an invite and its ``create`` audit row, atomically."""
    stamp = clock.iso_utc(created_at)
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO invites(email, is_admin, invited_by, token_hash, "
            "created_at, updated_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                email,
                int(is_admin),
                invited_by,
                token_hash,
                stamp,
                stamp,
                clock.iso_utc(expires_at),
            ),
        )
        invite = _require_live_invite(conn, int(cur.lastrowid or 0))
        write_audit(
            conn,
            entity_type=_ENTITY,
            entity_id=invite.id,
            operation="create",
            prev=None,
            new=_audit_payload(invite),
            request_ctx=request_ctx,
            actor_user_id=invited_by,
        )
    return invite


def rotate_token(
    conn: sqlite3.Connection,
    invite_id: int,
    *,
    token_hash: str,
    expires_at: datetime,
    now: datetime,
    actor_user_id: int,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> Invite:
    """Replace the token hash and expiry (resend); the old token stops resolving."""
    with transaction(conn):
        prev = _require_live_invite(conn, invite_id)
        conn.execute(
            "UPDATE invites SET token_hash = ?, expires_at = ?, updated_at = ? "
            "WHERE id = ? AND deleted_at IS NULL",
            (token_hash, clock.iso_utc(expires_at), clock.iso_utc(now), invite_id),
        )
        updated = _require_live_invite(conn, invite_id)
        write_audit(
            conn,
            entity_type=_ENTITY,
            entity_id=invite_id,
            operation="update",
            prev=_audit_payload(prev),
            new=_audit_payload(updated),
            request_ctx=request_ctx,
            actor_user_id=actor_user_id,
        )
    return updated


def _stamp(
    conn: sqlite3.Connection,
    invite_id: int,
    *,
    column: str,
    operation: str,
    now: datetime,
    actor_user_id: int,
    request_ctx: RequestCtx,
) -> Invite:
    with transaction(conn):
        prev = _require_live_invite(conn, invite_id)
        conn.execute(
            f"UPDATE invites SET {column} = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
            (clock.iso_utc(now), clock.iso_utc(now), invite_id),
        )
        updated = _require_live_invite(conn, invite_id)
        write_audit(
            conn,
            entity_type=_ENTITY,
            entity_id=invite_id,
            operation=operation,
            prev=_audit_payload(prev),
            new=_audit_payload(updated),
            request_ctx=request_ctx,
            actor_user_id=actor_user_id,
        )
    return updated


def mark_revoked(
    conn: sqlite3.Connection,
    invite_id: int,
    *,
    now: datetime,
    actor_user_id: int,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> Invite:
    """Set ``revoked_at`` (final) with a ``revoke`` audit row."""
    return _stamp(
        conn,
        invite_id,
        column="revoked_at",
        operation="update",
        now=now,
        actor_user_id=actor_user_id,
        request_ctx=request_ctx,
    )


def mark_used(
    conn: sqlite3.Connection,
    invite_id: int,
    *,
    now: datetime,
    actor_user_id: int,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> Invite:
    """Set ``used_at`` (the invitee accepted; ``actor_user_id`` is the new user)."""
    return _stamp(
        conn,
        invite_id,
        column="used_at",
        operation="update",
        now=now,
        actor_user_id=actor_user_id,
        request_ctx=request_ctx,
    )
