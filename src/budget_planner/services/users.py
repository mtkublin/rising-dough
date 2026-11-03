"""User lifecycle services (T-D19; extended by T-D17 / T-D18).

Admin bootstrap (ADR-0061 §3 as amended by ADR-0069):

- :func:`resolve_bootstrap_credentials` — pure, env → credentials policy.
- :func:`bootstrap_admin` — idempotent, runs against an open connection.
- :func:`bootstrap_admin_at_startup` — lifespan wrapper that opens / closes
  the connection and skips the DB entirely when the test env has no
  credentials.
- :func:`set_user_password` — operator CLI backend.

The plaintext password and the bcrypt hash are never logged or written to
``audit_log``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Literal

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.logging import get_logger
from budget_planner.repositories import auth_users as auth_users_repo, users as users_repo
from budget_planner.services import _passwords

DEV_ADMIN_EMAIL: Final = "admin@local.test"
DEV_ADMIN_PASSWORD: Final = "admin"  # noqa: S105 — documented dev default  # pragma: allowlist secret

BootstrapAction = Literal["created", "promoted", "noop"]
CredentialSource = Literal["env", "dev_default"]

_LOGGER_NAME: Final = "budget_planner.admin_bootstrap"


class BootstrapAdminMissingEnv(RuntimeError):  # noqa: N818 — name fixed by the T-D19 spec
    """No live admin exists and no bootstrap credentials are configured."""


class SchemaNotMigratedError(RuntimeError):
    """The ``users`` table predates migration 0012 (no ``is_admin`` column)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class BootstrapCredentials:
    email: str
    password: str
    must_change_password: bool
    source: CredentialSource

    def __repr__(self) -> str:  # never leak the password via repr / logs
        return (
            f"BootstrapCredentials(email={self.email!r}, password='***', "
            f"must_change_password={self.must_change_password}, source={self.source!r})"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class BootstrapOutcome:
    action: BootstrapAction
    user_id: int | None = None
    admin_email: str | None = None
    reason: str | None = None
    legacy_adopted: bool = False


def resolve_bootstrap_credentials(settings: Settings) -> BootstrapCredentials | None:
    """Return the credentials the bootstrap should use, or ``None``.

    Raises :class:`BootstrapAdminMissingEnv` when exactly one of the two
    env vars is set (half-configured deployment).
    """
    email = settings.admin_email
    password = (
        None
        if settings.admin_initial_password is None
        else settings.admin_initial_password.get_secret_value()
    )
    if email and password:
        return BootstrapCredentials(
            email=email, password=password, must_change_password=True, source="env"
        )
    if email or password:
        raise BootstrapAdminMissingEnv(
            "Both BUDGET_PLANNER_ADMIN_EMAIL and BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD "
            "must be set (only one is)."
        )
    if settings.env == "dev":
        return BootstrapCredentials(
            email=DEV_ADMIN_EMAIL,
            password=DEV_ADMIN_PASSWORD,
            must_change_password=False,
            source="dev_default",
        )
    return None


def _assert_schema(conn: sqlite3.Connection) -> None:
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "is_admin" not in cols:
        raise SchemaNotMigratedError(
            "users table is missing the multi-user columns — apply migrations "
            "(0012_multi_user.sql) before starting the app."
        )


def _emit(outcome: BootstrapOutcome, *, source: CredentialSource | None) -> BootstrapOutcome:
    level = "info" if outcome.reason in {None, "admin_exists"} else "warning"
    # Fresh proxy per call (cheap) so structlog's ``capture_logs`` sees it.
    log = get_logger(_LOGGER_NAME)
    getattr(log, level)(
        "admin_bootstrap",
        action=outcome.action,
        admin_email=outcome.admin_email,
        user_id=outcome.user_id,
        source=source,
        reason=outcome.reason,
        legacy_adopted=outcome.legacy_adopted,
    )
    return outcome


def _promote(
    conn: sqlite3.Connection,
    user_id: int,
    creds: BootstrapCredentials,
    *,
    set_email: bool,
) -> auth_users_repo.AuthUser:
    return users_repo.update_credentials(
        conn,
        user_id,
        update=users_repo.CredentialUpdate(
            password_hash=_passwords.hash_password(creds.password),
            must_change_password=creds.must_change_password,
            email=creds.email if set_email else None,
            is_admin=True,
        ),
    )


def bootstrap_admin(conn: sqlite3.Connection, settings: Settings) -> BootstrapOutcome:
    """Ensure a live admin exists (ADR-0061 §3, ADR-0069). Idempotent.

    Never touches any row when a live admin already exists. An unmigrated
    schema is fatal in production and a logged no-op elsewhere (so
    ``just dev --db=<new file>`` still boots before ``just migrate``).
    """
    try:
        _assert_schema(conn)
    except SchemaNotMigratedError:
        if settings.env == "production":
            raise
        return _emit(BootstrapOutcome(action="noop", reason="schema_not_migrated"), source=None)
    if users_repo.has_live_admin(conn):
        return _emit(BootstrapOutcome(action="noop", reason="admin_exists"), source=None)

    creds = resolve_bootstrap_credentials(settings)
    if creds is None:
        if settings.env == "production":
            raise BootstrapAdminMissingEnv(
                "No admin exists and BUDGET_PLANNER_ADMIN_EMAIL / "
                "BUDGET_PLANNER_ADMIN_INITIAL_PASSWORD are not set (ADR-0061 §3)."
            )
        return _emit(BootstrapOutcome(action="noop", reason="no_credentials"), source=None)
    return _emit(_apply_credentials(conn, creds), source=creds.source)


def _apply_credentials(conn: sqlite3.Connection, creds: BootstrapCredentials) -> BootstrapOutcome:
    """Promote / adopt / create per ADR-0069 §2 and §3. Caller logs the outcome."""
    existing = auth_users_repo.find_live_by_email(conn, creds.email)
    if existing is not None:
        promoted = _promote(conn, existing.id, creds, set_email=False)
        return BootstrapOutcome(action="promoted", user_id=promoted.id, admin_email=creds.email)

    legacy = users_repo.find_legacy_owner(conn)
    if legacy is not None:
        if creds.source == "dev_default" and users_repo.owns_accounts(conn, legacy.id):
            # ADR-0069 §3: never write a dev credential onto real data.
            return BootstrapOutcome(
                action="noop",
                user_id=legacy.id,
                admin_email=creds.email,
                reason="legacy_data_present",
            )
        promoted = _promote(conn, legacy.id, creds, set_email=True)
        return BootstrapOutcome(
            action="promoted",
            user_id=promoted.id,
            admin_email=creds.email,
            legacy_adopted=True,
        )

    created = users_repo.create_user(
        conn,
        data=users_repo.NewUser(
            name=creds.email.split("@", 1)[0],
            email=creds.email,
            password_hash=_passwords.hash_password(creds.password),
            is_admin=True,
            must_change_password=creds.must_change_password,
        ),
    )
    return BootstrapOutcome(action="created", user_id=created.id, admin_email=creds.email)


def bootstrap_admin_at_startup(
    settings: Settings,
    *,
    connect: Callable[[Settings], sqlite3.Connection] = get_connection,
) -> BootstrapOutcome:
    """Lifespan entry point: open a connection, bootstrap, close.

    In the ``test`` env without credentials the DB is not opened at all,
    so tests that boot the app against arbitrary paths stay side-effect
    free (ADR-0069 §1).
    """
    if settings.env == "test" and resolve_bootstrap_credentials(settings) is None:
        return _emit(BootstrapOutcome(action="noop", reason="no_credentials"), source=None)
    conn = connect(settings)
    try:
        return bootstrap_admin(conn, settings)
    finally:
        conn.close()


@dataclass(frozen=True, slots=True, kw_only=True)
class PasswordChange:
    """Operator-driven credential change (ADR-0069 §4)."""

    password: str
    must_change_password: bool
    set_email: str | None = None
    make_admin: bool = False


def set_user_password(
    conn: sqlite3.Connection, user_id: int, *, change: PasswordChange
) -> auth_users_repo.AuthUser:
    """Hash and store a new password for a live user; audit-logged.

    Raises ``ValueError`` for an invalid password, ``UserNotFoundError``
    for a missing user, ``sqlite3.IntegrityError`` on an email collision
    and :class:`SchemaNotMigratedError` on a pre-0012 DB.
    """
    _assert_schema(conn)
    password_hash = _passwords.hash_password(change.password)
    return users_repo.update_credentials(
        conn,
        user_id,
        update=users_repo.CredentialUpdate(
            password_hash=password_hash,
            must_change_password=change.must_change_password,
            email=None if change.set_email is None else change.set_email.strip().lower(),
            is_admin=True if change.make_admin else None,
        ),
    )


__all__ = [
    "DEV_ADMIN_EMAIL",
    "DEV_ADMIN_PASSWORD",
    "BootstrapAdminMissingEnv",
    "BootstrapCredentials",
    "BootstrapOutcome",
    "PasswordChange",
    "SchemaNotMigratedError",
    "bootstrap_admin",
    "bootstrap_admin_at_startup",
    "resolve_bootstrap_credentials",
    "set_user_password",
]
