"""Read-only user lookups for authentication (T-D02a, ADR-0061).

Kept separate from a future full ``users`` repository (T-D17 / T-D19) so the
auth stack can land first. Only live users (``deleted_at IS NULL``) are
ever returned. Email matching is case-insensitive, mirroring the
``ux_users_email_live`` index on ``lower(email)`` from migration 0012.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

_COLUMNS = "id, name, email, password_hash, is_admin, must_change_password"


@dataclass(frozen=True, slots=True, kw_only=True)
class AuthUser:
    """Identity + credential facts needed by the auth stack."""

    id: int
    name: str
    email: str | None
    password_hash: str | None
    is_admin: bool
    must_change_password: bool


def _hydrate(row: sqlite3.Row) -> AuthUser:
    return AuthUser(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        password_hash=row["password_hash"],
        is_admin=bool(row["is_admin"]),
        must_change_password=bool(row["must_change_password"]),
    )


def find_live_by_email(conn: sqlite3.Connection, email: str) -> AuthUser | None:
    """Return the live user whose email matches ``email`` case-insensitively."""
    normalized = email.strip().lower()
    if not normalized:
        return None
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM users WHERE lower(email) = ? AND deleted_at IS NULL",
        (normalized,),
    ).fetchone()
    return None if row is None else _hydrate(row)


def get_live_by_id(conn: sqlite3.Connection, user_id: int) -> AuthUser | None:
    """Return the live user with ``id = user_id``, or ``None``."""
    row = conn.execute(
        f"SELECT {_COLUMNS} FROM users WHERE id = ? AND deleted_at IS NULL",
        (user_id,),
    ).fetchone()
    return None if row is None else _hydrate(row)


__all__ = ["AuthUser", "find_live_by_email", "get_live_by_id"]
