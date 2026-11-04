"""Self-service password change (T-D18, ADR-0061 §4, ADR-0074).

- :func:`validate_new_password` — pure policy check (length, bcrypt byte
  limit, confirm match, differs from current).
- :func:`change_own_password` — verify the current password, then in one
  transaction store the new hash, clear ``must_change_password`` and revoke
  every *other* session of the user.

bcrypt work (verify + hash) runs outside the transaction so the SQLite write
lock is never held for the ~250 ms a cost-12 hash takes. Inside the
transaction the stored hash is re-read and compared, so a concurrent change
between verify and write is rejected rather than overwritten.

Plaintext passwords and hashes are never logged or written to ``audit_log``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from typing import Final, Literal

from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories import (
    auth_users as auth_users_repo,
    sessions as sessions_repo,
    users as users_repo,
)
from budget_planner.repositories._shared import transaction, write_audit
from budget_planner.services import _passwords

MIN_PASSWORD_LENGTH: Final = 12
MAX_PASSWORD_BYTES: Final = _passwords.MAX_PASSWORD_BYTES

AUTH_EVENT_ENTITY: Final = "auth_event"
SESSION_ENTITY: Final = "session"

Field = Literal["current_password", "new_password", "confirm_password"]
FailureReason = Literal["bad_current_password", "no_password"]

MSG_CURRENT_REQUIRED: Final = "Enter your current password."
MSG_CURRENT_WRONG: Final = "That isn't your current password."
MSG_TOO_SHORT: Final = f"Use at least {MIN_PASSWORD_LENGTH} characters."
MSG_TOO_LONG: Final = f"Use at most {MAX_PASSWORD_BYTES} bytes (bcrypt limit)."
MSG_SAME_AS_CURRENT: Final = "Pick a password different from your current one."
MSG_MISMATCH: Final = "The two new passwords don't match."
MSG_STALE: Final = "Your password changed in the meantime. Try again."


@dataclass(frozen=True, slots=True, kw_only=True)
class FieldError:
    """One validation failure bound to a form field."""

    field: Field
    message: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PasswordChangeRequest:
    """The three form inputs, verbatim (no trimming)."""

    current_password: str
    new_password: str
    confirm_password: str

    def __repr__(self) -> str:  # never leak plaintext via repr / logs
        return "PasswordChangeRequest(current_password='***', new_password='***', ...)"


@dataclass(frozen=True, slots=True, kw_only=True)
class PasswordChangeOutcome:
    """Result of :func:`change_own_password`. ``ok`` iff ``errors`` is empty."""

    errors: tuple[FieldError, ...] = ()
    revoked_sessions: int = 0

    @property
    def ok(self) -> bool:
        return not self.errors

    def message_for(self, field: Field) -> str | None:
        """Return the first error message for ``field``, if any."""
        return next((e.message for e in self.errors if e.field == field), None)


def validate_new_password(req: PasswordChangeRequest) -> tuple[FieldError, ...]:
    """Return every ADR-0074 §1 policy violation for ``req`` (pure)."""
    errors: list[FieldError] = []
    new = req.new_password
    if len(new) < MIN_PASSWORD_LENGTH:
        errors.append(FieldError(field="new_password", message=MSG_TOO_SHORT))
    elif len(new.encode("utf-8")) > MAX_PASSWORD_BYTES:
        errors.append(FieldError(field="new_password", message=MSG_TOO_LONG))
    elif req.current_password and new == req.current_password:
        errors.append(FieldError(field="new_password", message=MSG_SAME_AS_CURRENT))
    if req.confirm_password != new:
        errors.append(FieldError(field="confirm_password", message=MSG_MISMATCH))
    return tuple(errors)


def _audit_failure(
    conn: sqlite3.Connection, user_id: int, reason: FailureReason, ctx: RequestCtx
) -> None:
    with transaction(conn):
        write_audit(
            conn,
            entity_type=AUTH_EVENT_ENTITY,
            entity_id=user_id,
            operation="create",
            prev=None,
            new={"event": "password_change_failed", "reason": reason},
            request_ctx=replace(ctx, user_id=user_id),
        )


def _commit_change(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    verified_hash: str,
    new_hash: str,
    current_session_id: str | None,
    ctx: RequestCtx,
) -> int | None:
    """Write the new credential + revoke other sessions atomically.

    Returns the number of revoked sessions, or ``None`` when the stored hash
    no longer matches ``verified_hash`` (nothing is written).
    """
    with transaction(conn):
        user = auth_users_repo.get_live_by_id(conn, user_id)
        if user is None or user.password_hash != verified_hash:
            return None
        users_repo.update_credentials(
            conn,
            user_id,
            update=users_repo.CredentialUpdate(password_hash=new_hash, must_change_password=False),
            request_ctx=ctx,
        )
        revoked = sessions_repo.revoke_all_user_sessions(
            conn, user_id, except_token=current_session_id
        )
        if revoked:
            write_audit(
                conn,
                entity_type=SESSION_ENTITY,
                entity_id=user_id,
                operation="delete",
                prev={"event": "password_change_revoke_others", "count": revoked},
                new=None,
                request_ctx=ctx,
            )
    return revoked


def change_own_password(
    conn: sqlite3.Connection,
    user_id: int,
    req: PasswordChangeRequest,
    *,
    current_session_id: str | None,
    request_ctx: RequestCtx,
) -> PasswordChangeOutcome:
    """Rotate ``user_id``'s own password (ADR-0074 §2).

    Raises :class:`~budget_planner.repositories.users.UserNotFoundError` if
    the user is missing or soft-deleted.
    """
    policy_errors = validate_new_password(req)
    if not req.current_password:
        current_error = FieldError(field="current_password", message=MSG_CURRENT_REQUIRED)
        return PasswordChangeOutcome(errors=(current_error, *policy_errors))

    user = auth_users_repo.get_live_by_id(conn, user_id)
    if user is None:
        raise users_repo.UserNotFoundError(f"no live user with id {user_id}")
    if not user.password_hash or not _passwords.verify_password(
        req.current_password, user.password_hash
    ):
        reason: FailureReason = "bad_current_password" if user.password_hash else "no_password"
        _audit_failure(conn, user_id, reason, request_ctx)
        wrong = FieldError(field="current_password", message=MSG_CURRENT_WRONG)
        return PasswordChangeOutcome(errors=(wrong, *policy_errors))
    if policy_errors:
        return PasswordChangeOutcome(errors=policy_errors)

    new_hash = _passwords.hash_password(req.new_password)
    revoked = _commit_change(
        conn,
        user_id,
        verified_hash=user.password_hash,
        new_hash=new_hash,
        current_session_id=current_session_id,
        ctx=request_ctx,
    )
    if revoked is None:
        return PasswordChangeOutcome(
            errors=(FieldError(field="current_password", message=MSG_STALE),)
        )
    return PasswordChangeOutcome(revoked_sessions=revoked)


__all__ = [
    "MAX_PASSWORD_BYTES",
    "MIN_PASSWORD_LENGTH",
    "FieldError",
    "PasswordChangeOutcome",
    "PasswordChangeRequest",
    "change_own_password",
    "validate_new_password",
]
