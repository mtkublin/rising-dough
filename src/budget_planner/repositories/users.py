"""Write-side ``users`` repository (T-D19, ADR-0061 §3/§6, ADR-0069).

Read lookups used by the auth stack live in
:mod:`budget_planner.repositories.auth_users` and are reused here, not
duplicated. This module adds the mutations needed by the admin bootstrap,
the operator password CLI and the T-D17 admin panel (``list_live``,
``count_live_admins``, ``update_profile``, ``reset_password``,
``soft_delete``).

``users`` is not a user-owned table (it *is* the owner), so functions
targeting one row follow the ``(conn, user_id, ...)`` convention, and
roster-wide predicates (``has_live_admin``) take only ``conn``.

Every mutation runs in one transaction with its ``audit_log`` row(s).
Audit payloads never carry ``password_hash`` (or a plaintext): they record
``password_set`` instead. Admin-panel mutations also pass
``actor_user_id`` (ADR-0073 §5).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from budget_planner.domain.enums import Direction
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.domain.system_categories import (
    RECONCILIATION_CATEGORY_NAME,
    TRANSIT_CATEGORY_NAME,
)
from budget_planner.repositories import sessions as sessions_repo
from budget_planner.repositories._shared import (
    parse_dt,
    parse_dt_required,
    transaction,
    utc_now_iso,
    write_audit,
)
from budget_planner.repositories.auth_users import (
    AuthUser,
    find_live_by_email,
    get_live_by_id,
)

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


@dataclass(frozen=True, slots=True, kw_only=True)
class ProfileUpdate:
    """Input for :func:`update_profile` (admin edit: email, name, admin flag)."""

    email: str
    name: str
    is_admin: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class UserListing:
    """One row of the admin roster (no credential material)."""

    id: int
    name: str
    email: str | None
    is_admin: bool
    must_change_password: bool
    created_at: datetime
    last_seen_at: datetime | None


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
    conn: sqlite3.Connection,
    user_id: int,
    request_ctx: RequestCtx,
    actor_user_id: int | None,
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
            actor_user_id=actor_user_id,
        )


def create_user(
    conn: sqlite3.Connection,
    *,
    data: NewUser,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
    actor_user_id: int | None = None,
) -> AuthUser:
    """Insert a user plus its two system categories, atomically, with audit rows.

    Lets ``sqlite3.IntegrityError`` through on a live-email collision.
    """
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
            actor_user_id=actor_user_id,
        )
        _seed_system_categories(conn, user_id, request_ctx, actor_user_id)
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


def count_live_admins(conn: sqlite3.Connection) -> int:
    """Return the number of live admins (ADR-0061 §1 last-admin invariant)."""
    row = conn.execute(
        "SELECT count(*) AS n FROM users WHERE is_admin = 1 AND deleted_at IS NULL"
    ).fetchone()
    return int(row["n"])


def get_by_email_live(conn: sqlite3.Connection, email: str) -> AuthUser | None:
    """Return the live user with ``email`` (case-insensitive), or ``None``."""
    return find_live_by_email(conn, email)


def _hydrate_listing(row: sqlite3.Row) -> UserListing:
    return UserListing(
        id=int(row["id"]),
        name=row["name"],
        email=row["email"],
        is_admin=bool(row["is_admin"]),
        must_change_password=bool(row["must_change_password"]),
        created_at=parse_dt_required(row["created_at"]),
        last_seen_at=parse_dt(row["last_seen_at"]),
    )


def list_live(conn: sqlite3.Connection) -> list[UserListing]:
    """Return every live user, ordered by email (then id), for the admin roster.

    ``last_seen_at`` is the most recent ``sessions.last_seen_at`` of the user
    (any session, revoked or not), or ``None`` if they never signed in.
    """
    rows = conn.execute(
        "SELECT u.id, u.name, u.email, u.is_admin, u.must_change_password, u.created_at, "
        "(SELECT max(s.last_seen_at) FROM sessions AS s WHERE s.user_id = u.id) "
        "AS last_seen_at "
        "FROM users AS u WHERE u.deleted_at IS NULL "
        "ORDER BY lower(coalesce(u.email, u.name)), u.id"
    ).fetchall()
    return [_hydrate_listing(r) for r in rows]


def update_profile(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    update: ProfileUpdate,
    actor_user_id: int,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> AuthUser:
    """Set a live user's email, name and admin flag; audit-logged.

    Raises :class:`UserNotFoundError` for a missing / soft-deleted user and
    lets ``sqlite3.IntegrityError`` through on a live-email collision.
    """
    with transaction(conn):
        prev = _require_live(conn, user_id)
        conn.execute(
            "UPDATE users SET email = ?, name = ?, is_admin = ?, updated_at = ? "
            "WHERE id = ? AND deleted_at IS NULL",
            (update.email, update.name, int(update.is_admin), utc_now_iso(), user_id),
        )
        updated = _require_live(conn, user_id)
        write_audit(
            conn,
            entity_type="users",
            entity_id=user_id,
            operation="update",
            prev=_redacted(prev),
            new=_redacted(updated),
            request_ctx=request_ctx,
            actor_user_id=actor_user_id,
        )
    return updated


def reset_password(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    password_hash: str,
    actor_user_id: int,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> AuthUser:
    """Store a new hash, force rotation and revoke every live session, atomically.

    Audit row: ``operation='update'`` with ``action='reset_password'`` and the
    number of revoked sessions (ADR-0073 §6). Raises
    :class:`UserNotFoundError` for a missing / soft-deleted user.
    """
    with transaction(conn):
        prev = _require_live(conn, user_id)
        conn.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 1, updated_at = ? "
            "WHERE id = ? AND deleted_at IS NULL",
            (password_hash, utc_now_iso(), user_id),
        )
        revoked = sessions_repo.revoke_all_user_sessions(conn, user_id)
        updated = _require_live(conn, user_id)
        write_audit(
            conn,
            entity_type="users",
            entity_id=user_id,
            operation="update",
            prev=_redacted(prev),
            new={**_redacted(updated), "action": "reset_password", "sessions_revoked": revoked},
            request_ctx=request_ctx,
            actor_user_id=actor_user_id,
        )
    return updated


def soft_delete(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    actor_user_id: int,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> AuthUser:
    """Soft-delete a live user and revoke all their sessions in one transaction.

    Returns the user as it was before deletion. Raises
    :class:`UserNotFoundError` for a missing / already-deleted user.
    """
    with transaction(conn):
        prev = _require_live(conn, user_id)
        now = utc_now_iso()
        conn.execute(
            "UPDATE users SET deleted_at = ?, updated_at = ? WHERE id = ? AND deleted_at IS NULL",
            (now, now, user_id),
        )
        sessions_repo.revoke_all_user_sessions(conn, user_id)
        write_audit(
            conn,
            entity_type="users",
            entity_id=user_id,
            operation="delete",
            prev=_redacted(prev),
            new=None,
            request_ctx=request_ctx,
            actor_user_id=actor_user_id,
        )
    return prev


__all__ = [
    "SYSTEM_CATEGORY_SEEDS",
    "CredentialUpdate",
    "NewUser",
    "ProfileUpdate",
    "UserListing",
    "UserNotFoundError",
    "count_live_admins",
    "create_user",
    "find_legacy_owner",
    "get_by_email_live",
    "has_live_admin",
    "list_live",
    "owns_accounts",
    "reset_password",
    "soft_delete",
    "update_credentials",
    "update_profile",
]
