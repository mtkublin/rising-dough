"""User lifecycle services (T-D19; extended by T-D17 / T-D18).

Admin bootstrap (ADR-0061 §3 as amended by ADR-0069):

- :func:`resolve_bootstrap_credentials` — pure, env → credentials policy.
- :func:`bootstrap_admin` — idempotent, runs against an open connection.
- :func:`bootstrap_admin_at_startup` — lifespan wrapper that opens / closes
  the connection and skips the DB entirely when the test env has no
  credentials.
- :func:`set_user_password` — operator CLI backend.

Admin panel (T-D17, ADR-0061 §1/§4, ADR-0073):

- :func:`list_live_users`, :func:`get_live_user` — roster reads.
- :func:`create_user`, :func:`reset_password` — return the one-shot
  generated plaintext alongside the user; it is never stored or logged.
- :func:`edit_user`, :func:`soft_delete_user` — enforce the last-admin
  invariant, live-email uniqueness and the no-self-removal rule.

The plaintext password and the bcrypt hash are never logged or written to
``audit_log``.
"""

from __future__ import annotations

import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Literal

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.logging import get_logger
from budget_planner.repositories import auth_users as auth_users_repo, users as users_repo
from budget_planner.repositories._shared import transaction
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


# --------------------------------------------------------------------------
# Admin panel (T-D17)
# --------------------------------------------------------------------------

#: ``secrets.token_urlsafe(16)`` → 22 chars, ~128 bits (ADR-0061 §8).
GENERATED_PASSWORD_BYTES: Final = 16
EMAIL_MAX_LENGTH: Final = 254
NAME_MAX_LENGTH: Final = 100

LAST_ADMIN_DELETE_MESSAGE: Final = (
    "Can't remove the last admin. Promote another user to admin first."
)
LAST_ADMIN_DEMOTE_MESSAGE: Final = (
    "Can't remove admin rights from the last admin. Promote another user first."
)
SELF_DELETE_MESSAGE: Final = "You can't remove your own account. Ask another admin."
DUPLICATE_EMAIL_MESSAGE: Final = "Another user already has this email."
INVALID_EMAIL_MESSAGE: Final = "Enter a valid email address."
NAME_TOO_LONG_MESSAGE: Final = f"Name must be at most {NAME_MAX_LENGTH} characters."

_EMPTY_REQUEST_CTX: Final = RequestCtx.empty()


class UserAdminError(Exception):
    """Base for admin-panel refusals; the router maps each subclass to a status.

    Plain (non-frozen) exceptions on purpose: frozen-dataclass errors cannot
    be re-raised through ``contextmanager`` / generator dependencies, which
    assign ``__traceback__``.
    """


class UserNotFound(UserAdminError):  # noqa: N818 — reads as a status, maps to 404
    """Target user is missing or soft-deleted (404)."""

    def __init__(self, user_id: int) -> None:
        super().__init__(f"user {user_id} not found")
        self.user_id = user_id


class UserConflict(UserAdminError):  # noqa: N818 — maps to 409
    """Roster invariant refusal: last admin, self-removal (409, ADR-0073 §3)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UserInputError(UserAdminError):
    """Invalid or duplicate input, keyed by form field (422)."""

    def __init__(self, fields: dict[str, str]) -> None:
        super().__init__("; ".join(f"{k}: {v}" for k, v in fields.items()))
        self.fields = dict(fields)


@dataclass(frozen=True, slots=True, kw_only=True)
class UserDraft:
    """Validated admin input for add / edit. ``email`` is lower-cased."""

    email: str
    name: str
    is_admin: bool


def generate_password() -> str:
    """Return a fresh one-shot password (ADR-0061 §8)."""
    return secrets.token_urlsafe(GENERATED_PASSWORD_BYTES)


def _valid_email(email: str) -> bool:
    if not email or len(email) > EMAIL_MAX_LENGTH or any(c.isspace() for c in email):
        return False
    local, sep, domain = email.partition("@")
    return bool(sep and local and domain and "@" not in domain and "." in domain.strip("."))


def build_draft(*, email: str, name: str, is_admin: bool) -> UserDraft:
    """Normalise + validate raw form input. Pure.

    Raises :class:`UserInputError` keyed by field name. An empty name falls
    back to the email's local part.
    """
    normalized_email = email.strip().lower()
    errors: dict[str, str] = {}
    if not _valid_email(normalized_email):
        errors["email"] = INVALID_EMAIL_MESSAGE
    clean_name = " ".join(name.split())
    if len(clean_name) > NAME_MAX_LENGTH:
        errors["name"] = NAME_TOO_LONG_MESSAGE
    if errors:
        raise UserInputError(errors)
    return UserDraft(
        email=normalized_email,
        name=clean_name or normalized_email.split("@", 1)[0],
        is_admin=is_admin,
    )


def list_live_users(conn: sqlite3.Connection) -> list[users_repo.UserListing]:
    """Admin roster: every live user (no credential material)."""
    return users_repo.list_live(conn)


def get_live_user(conn: sqlite3.Connection, user_id: int) -> auth_users_repo.AuthUser:
    """Return the live user or raise :class:`UserNotFound`."""
    user = auth_users_repo.get_live_by_id(conn, user_id)
    if user is None:
        raise UserNotFound(user_id)
    return user


def _atomically[T](conn: sqlite3.Connection, body: Callable[[], T]) -> T:
    """Run ``body`` in one transaction; map a live-email race to :class:`UserInputError`."""
    try:
        with transaction(conn):
            return body()
    except sqlite3.IntegrityError as exc:  # ux_users_email_live race
        raise UserInputError({"email": DUPLICATE_EMAIL_MESSAGE}) from exc


def _require_target(conn: sqlite3.Connection, user_id: int) -> auth_users_repo.AuthUser:
    user = auth_users_repo.get_live_by_id(conn, user_id)
    if user is None:
        raise UserNotFound(user_id)
    return user


def _ensure_email_free(conn: sqlite3.Connection, email: str, *, own_id: int | None) -> None:
    holder = users_repo.get_by_email_live(conn, email)
    if holder is not None and holder.id != own_id:
        raise UserInputError({"email": DUPLICATE_EMAIL_MESSAGE})


def _is_last_admin(conn: sqlite3.Connection, user: auth_users_repo.AuthUser) -> bool:
    return user.is_admin and users_repo.count_live_admins(conn) <= 1


def create_user(
    conn: sqlite3.Connection,
    actor_user_id: int,
    draft: UserDraft,
    *,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> tuple[auth_users_repo.AuthUser, str]:
    """Create a user with a generated password + its system categories.

    Returns ``(user, plaintext)``; the plaintext is for the one-shot toast
    only. Raises :class:`UserInputError` on a duplicate live email.
    """
    password = generate_password()
    password_hash = _passwords.hash_password(password)

    def _body() -> auth_users_repo.AuthUser:
        _ensure_email_free(conn, draft.email, own_id=None)
        return users_repo.create_user(
            conn,
            data=users_repo.NewUser(
                name=draft.name,
                email=draft.email,
                password_hash=password_hash,
                is_admin=draft.is_admin,
                must_change_password=True,
            ),
            request_ctx=request_ctx,
            actor_user_id=actor_user_id,
        )

    return _atomically(conn, _body), password


def edit_user(
    conn: sqlite3.Connection,
    actor_user_id: int,
    user_id: int,
    draft: UserDraft,
    *,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> auth_users_repo.AuthUser:
    """Update email / name / admin flag of a live user.

    Raises :class:`UserNotFound`, :class:`UserInputError` (duplicate email)
    or :class:`UserConflict` (demoting the last admin).
    """

    def _body() -> auth_users_repo.AuthUser:
        target = _require_target(conn, user_id)
        _ensure_email_free(conn, draft.email, own_id=target.id)
        if not draft.is_admin and _is_last_admin(conn, target):
            raise UserConflict(LAST_ADMIN_DEMOTE_MESSAGE)
        return users_repo.update_profile(
            conn,
            user_id,
            update=users_repo.ProfileUpdate(
                email=draft.email, name=draft.name, is_admin=draft.is_admin
            ),
            actor_user_id=actor_user_id,
            request_ctx=request_ctx,
        )

    return _atomically(conn, _body)


def reset_password(
    conn: sqlite3.Connection,
    actor_user_id: int,
    user_id: int,
    *,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> tuple[auth_users_repo.AuthUser, str]:
    """Generate a new password, force rotation, revoke the target's sessions.

    Returns ``(user, plaintext)`` for the one-shot toast. Raises
    :class:`UserNotFound` for a missing / soft-deleted user.
    """
    get_live_user(conn, user_id)  # fail fast before paying for bcrypt
    password = generate_password()
    password_hash = _passwords.hash_password(password)

    def _body() -> auth_users_repo.AuthUser:
        _require_target(conn, user_id)
        return users_repo.reset_password(
            conn,
            user_id,
            password_hash=password_hash,
            actor_user_id=actor_user_id,
            request_ctx=request_ctx,
        )

    return _atomically(conn, _body), password


def soft_delete_user(
    conn: sqlite3.Connection,
    actor_user_id: int,
    user_id: int,
    *,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> auth_users_repo.AuthUser:
    """Soft-delete a user and revoke all their sessions (one transaction).

    Raises :class:`UserConflict` for self-removal (ADR-0073 §4) or when the
    target is the last live admin; :class:`UserNotFound` for a missing user.
    """
    if user_id == actor_user_id:
        raise UserConflict(SELF_DELETE_MESSAGE)

    def _body() -> auth_users_repo.AuthUser:
        target = _require_target(conn, user_id)
        if _is_last_admin(conn, target):
            raise UserConflict(LAST_ADMIN_DELETE_MESSAGE)
        return users_repo.soft_delete(
            conn, user_id, actor_user_id=actor_user_id, request_ctx=request_ctx
        )

    return _atomically(conn, _body)


__all__ = [
    "DEV_ADMIN_EMAIL",
    "DEV_ADMIN_PASSWORD",
    "DUPLICATE_EMAIL_MESSAGE",
    "GENERATED_PASSWORD_BYTES",
    "LAST_ADMIN_DELETE_MESSAGE",
    "LAST_ADMIN_DEMOTE_MESSAGE",
    "SELF_DELETE_MESSAGE",
    "BootstrapAdminMissingEnv",
    "BootstrapCredentials",
    "BootstrapOutcome",
    "PasswordChange",
    "SchemaNotMigratedError",
    "UserAdminError",
    "UserConflict",
    "UserDraft",
    "UserInputError",
    "UserNotFound",
    "bootstrap_admin",
    "bootstrap_admin_at_startup",
    "build_draft",
    "create_user",
    "edit_user",
    "generate_password",
    "get_live_user",
    "list_live_users",
    "reset_password",
    "resolve_bootstrap_credentials",
    "set_user_password",
    "soft_delete_user",
]
