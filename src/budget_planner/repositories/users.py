"""Write-side ``users`` repository (T-D19, ADR-0061 §3/§6, ADR-0069).

Read lookups used by the auth stack live in
:mod:`budget_planner.repositories.auth_users` and are reused here, not
duplicated. This module adds the mutations needed by the admin bootstrap
and the operator password CLI; T-D17 (admin panel) extends it.

``users`` is not a user-owned table (it *is* the owner), so functions
targeting one row follow the ``(conn, user_id, ...)`` convention, and
roster-wide predicates (``has_live_admin``) take only ``conn``.

Every mutation runs in one transaction with its ``audit_log`` row(s).
Audit payloads never carry ``password_hash`` (or a plaintext): they record
``password_set`` instead.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from budget_planner.domain.enums import Direction
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.domain.system_categories import (
    RECONCILIATION_CATEGORY_NAME,
    TRANSIT_CATEGORY_NAME,
)
from budget_planner.repositories._shared import (
    transaction,
    utc_now_iso,
    write_audit,
)
from budget_planner.repositories.auth_users import AuthUser, get_live_by_id

_EMPTY_REQUEST_CTX: RequestCtx = RequestCtx.empty()

# Mirrors ``migrations/0003_seed_system_rows.sql`` (ADR-0061 §6).
SYSTEM_CATEGORY_SEEDS: tuple[tuple[str, Direction], ...] = (
    (TRANSIT_CATEGORY_NAME, Direction.TRANSIT),
    (RECONCILIATION_CATEGORY_NAME, Direction.ADJUSTMENT),
)


@dataclass(frozen=True, slots=True, kw_only=True)
class NewUser:
    """Input for :func:`create_user`. ``password_hash`` is already bcrypt."""

    name: str
    email: str
    password_hash: str
    is_admin: bool
    must_change_password: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class CredentialUpdate:
    """Input for :func:`update_credentials`.

    ``email`` / ``is_admin`` of ``None`` leave the column unchanged.
    """

    password_hash: str
    must_change_password: bool
    email: str | None = None
    is_admin: bool | None = None


class UserNotFoundError(LookupError):
    """Raised when the target user is missing or soft-deleted."""


def _redacted(user: AuthUser) -> dict[str, object]:
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "is_admin": user.is_admin,
        "must_change_password": user.must_change_password,
        "password_set": user.password_hash is not None,
    }


def _require_live(conn: sqlite3.Connection, user_id: int) -> AuthUser:
    user = get_live_by_id(conn, user_id)
    if user is None:
        raise UserNotFoundError(f"no live user with id {user_id}")
    return user


def has_live_admin(conn: sqlite3.Connection) -> bool:
    """Return ``True`` iff at least one live admin exists (ADR-0061 §1)."""
    row = conn.execute(
        "SELECT 1 FROM users WHERE is_admin = 1 AND deleted_at IS NULL LIMIT 1"
    ).fetchone()
    return row is not None


def find_legacy_owner(conn: sqlite3.Connection) -> AuthUser | None:
    """Return the lowest-id live, non-admin user with no email.

    This is the pre-v3 ``id = 1`` row carried forward by migration 0012
    (ADR-0061 §2, ADR-0069 §2).
    """
    row = conn.execute(
        "SELECT id FROM users "
        "WHERE email IS NULL AND is_admin = 0 AND deleted_at IS NULL "
        "ORDER BY id LIMIT 1"
    ).fetchone()
    return None if row is None else get_live_by_id(conn, int(row["id"]))


def owns_accounts(conn: sqlite3.Connection, user_id: int) -> bool:
    """Return ``True`` iff ``user_id`` owns at least one account (live or not)."""
    row = conn.execute("SELECT 1 FROM accounts WHERE user_id = ? LIMIT 1", (user_id,)).fetchone()
    return row is not None


def _seed_system_categories(
    conn: sqlite3.Connection, user_id: int, request_ctx: RequestCtx
) -> None:
    for name, direction in SYSTEM_CATEGORY_SEEDS:
        cur = conn.execute(
            "INSERT INTO categories(user_id, name, direction, is_system) VALUES (?, ?, ?, 1)",
            (user_id, name, direction.value),
        )
        write_audit(
            conn,
            entity_type="categories",
            entity_id=int(cur.lastrowid or 0),
            operation="create",
            prev=None,
            new={"user_id": user_id, "name": name, "direction": direction.value, "is_system": True},
            request_ctx=request_ctx,
        )


def create_user(
    conn: sqlite3.Connection,
    *,
    data: NewUser,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> AuthUser:
    """Insert a user plus its two system categories, atomically, with audit rows."""
    with transaction(conn):
        cur = conn.execute(
            "INSERT INTO users(name, email, password_hash, is_admin, must_change_password) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                data.name,
                data.email,
                data.password_hash,
                int(data.is_admin),
                int(data.must_change_password),
            ),
        )
        user_id = int(cur.lastrowid or 0)
        created = _require_live(conn, user_id)
        write_audit(
            conn,
            entity_type="users",
            entity_id=user_id,
            operation="create",
            prev=None,
            new=_redacted(created),
            request_ctx=request_ctx,
        )
        _seed_system_categories(conn, user_id, request_ctx)
    return created


def update_credentials(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    update: CredentialUpdate,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> AuthUser:
    """Set a live user's password hash and rotation flag; optionally email / admin.

    Raises :class:`UserNotFoundError` for a missing or soft-deleted user and
    lets ``sqlite3.IntegrityError`` through when ``email`` collides with
    another live user (``ux_users_email_live``).
    """
    with transaction(conn):
        prev = _require_live(conn, user_id)
        conn.execute(
            "UPDATE users SET "
            "password_hash = ?, must_change_password = ?, "
            "email = COALESCE(?, email), is_admin = COALESCE(?, is_admin), "
            "updated_at = ? "
            "WHERE id = ? AND deleted_at IS NULL",
            (
                update.password_hash,
                int(update.must_change_password),
                update.email,
                None if update.is_admin is None else int(update.is_admin),
                utc_now_iso(),
                user_id,
            ),
        )
        updated = _require_live(conn, user_id)
        write_audit(
            conn,
            entity_type="users",
            entity_id=user_id,
            operation="update",
            prev=_redacted(prev),
            new={**_redacted(updated), "password_changed": True},
            request_ctx=request_ctx,
        )
    return updated


__all__ = [
    "SYSTEM_CATEGORY_SEEDS",
    "CredentialUpdate",
    "NewUser",
    "UserNotFoundError",
    "create_user",
    "find_legacy_owner",
    "has_live_admin",
    "owns_accounts",
    "update_credentials",
]
