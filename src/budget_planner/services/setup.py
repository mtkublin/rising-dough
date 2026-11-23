"""First-run setup: open predicate, token check, consume (T-UR32, ADR-0134 section 9).

The drill workflow generates a one-time token and passes only its hash to the
app as ``BUDGET_PLANNER_SETUP_TOKEN_HASH`` (lowercase hex sha256 of the token;
unset = setup closed). The app stores no token, only a consumed marker. The
token and its hash are never logged. Settings come in as arguments; this
module reads no env and no clock of its own.
"""

from __future__ import annotations

import hashlib
import hmac
import sqlite3
from dataclasses import dataclass
from typing import Protocol

from budget_planner.domain.ports import PasswordHasher
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.logging import get_logger
from budget_planner.repositories import setup as setup_repo, users as users_repo
from budget_planner.repositories._shared import transaction
from budget_planner.repositories.auth_users import AuthUser
from budget_planner.services.password_change import MIN_PASSWORD_LENGTH, MSG_TOO_SHORT
from budget_planner.services.users import (
    BootstrapAdminMissingEnv,
    BootstrapSettings,
    UserInputError,
    build_draft,
    resolve_bootstrap_credentials,
)

MSG_CONFIRM_MISMATCH = "The two passwords do not match."
_LOGGER_NAME = "budget_planner.setup"
_EMPTY_REQUEST_CTX: RequestCtx = RequestCtx.empty()


class SetupSettings(BootstrapSettings, Protocol):
    """The slice of ``Settings`` first-run setup reads."""

    @property
    def planner_setup_token_hash(self) -> str | None: ...


class SetupClosedError(Exception):
    """Setup is not open, or the token is wrong (indistinguishable on purpose)."""


@dataclass(frozen=True, slots=True, kw_only=True)
class SetupDraft:
    """Raw first-admin form input."""

    email: str
    name: str
    password: str
    password_confirm: str


def hash_token(token: str) -> str:
    """Lowercase hex sha256 of ``token``: the value operators put in config."""
    return hashlib.sha256(token.encode()).hexdigest()


def _bootstrap_admin_configured(settings: BootstrapSettings) -> bool:
    try:
        return resolve_bootstrap_credentials(settings) is not None
    except BootstrapAdminMissingEnv:
        get_logger(_LOGGER_NAME).warning("setup_closed_half_configured_bootstrap")
        return True  # half-configured bootstrap: stay closed


def is_open(conn: sqlite3.Connection, settings: SetupSettings) -> bool:
    """Setup is open: hash configured, not consumed, no users, no bootstrap admin."""
    if not settings.planner_setup_token_hash:
        return False
    if _bootstrap_admin_configured(settings):
        return False
    if setup_repo.is_consumed(conn):
        return False
    return not setup_repo.has_credentialed_user(conn)


def check_token(conn: sqlite3.Connection, settings: SetupSettings, token: str) -> bool:
    """``True`` iff setup is open and ``token`` hashes to the configured hash."""
    candidate = hash_token(token)
    expected = settings.planner_setup_token_hash or ""
    matches = hmac.compare_digest(candidate.encode(), expected.encode())
    return is_open(conn, settings) and matches


def _validate(draft: SetupDraft) -> None:
    errors: dict[str, str] = {}
    try:
        build_draft(email=draft.email, name=draft.name, is_admin=True)
    except UserInputError as exc:
        errors.update(exc.fields)
    if len(draft.password) < MIN_PASSWORD_LENGTH:
        errors["password"] = MSG_TOO_SHORT
    elif draft.password != draft.password_confirm:
        errors["password_confirm"] = MSG_CONFIRM_MISMATCH
    if errors:
        raise UserInputError(errors)


def complete_setup(
    conn: sqlite3.Connection,
    settings: SetupSettings,
    *,
    token: str,
    draft: SetupDraft,
    hasher: PasswordHasher,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> AuthUser:
    """Create the first admin and consume the token in one transaction.

    Raises :class:`SetupClosedError` for a closed setup or a wrong token (checked
    first, no oracle), then :class:`UserInputError` keyed by field.
    """
    log = get_logger(_LOGGER_NAME)
    with transaction(conn):
        if not check_token(conn, settings, token):
            log.warning("setup_rejected")
            raise SetupClosedError
        _validate(draft)
        parsed = build_draft(email=draft.email, name=draft.name, is_admin=True)
        admin = users_repo.create_user(
            conn,
            data=users_repo.NewUser(
                name=parsed.name,
                email=parsed.email,
                password_hash=hasher.hash(draft.password),
                is_admin=True,
                must_change_password=False,
            ),
            request_ctx=request_ctx,
        )
        setup_repo.mark_consumed(conn, user_id=admin.id, request_ctx=request_ctx)
    log.info("setup_completed", user_id=admin.id)
    return admin


__all__ = [
    "MSG_CONFIRM_MISMATCH",
    "SetupClosedError",
    "SetupDraft",
    "SetupSettings",
    "check_token",
    "complete_setup",
    "hash_token",
    "is_open",
]
