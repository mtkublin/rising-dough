"""Invites: create, resend, revoke, accept, link state (T-UR30, ADR-0134 section 1 and 10).

An admin invites a person by email and role. The plain token is returned to the
caller once (``IssuedInvite.token``; the mail port of T-UR31 and the copy-link
UI use it) and only ``sha256(token)`` is stored. The token and its hash are
never logged. Clock, entropy and hashing come in as arguments (ADR-0021).

Lifecycle: ``pending`` -> ``used`` (accepted) | revoked (final, reads as
``invalid``) | ``expired`` (resend revives it with a new token and expiry).
"""

from __future__ import annotations

import hmac
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal

from budget_planner.domain.ports import PasswordHasher, TokenSource
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories import (
    invites as invites_repo,
    sessions as sessions_repo,
    users as users_repo,
)
from budget_planner.repositories._shared import transaction
from budget_planner.repositories.auth_users import AuthUser
from budget_planner.repositories.invites import Invite
from budget_planner.services import users as users_service

#: An invite link works for 7 days from create or resend (ADR-0134 section 1).
INVITE_LIFETIME: Final = timedelta(days=7)
INVITE_TOKEN_BYTES: Final = 32

PENDING_INVITE_MESSAGE: Final = "This email already has a pending invite."
INVITE_NOT_FOUND_MESSAGE: Final = "Invite not found."
INVITE_FINAL_MESSAGE: Final = "This invite was already used or revoked. Create a new one."
INVITE_LINK_UNUSABLE_MESSAGE: Final = "This invite link can't be used."

InviteLinkState = Literal["pending", "expired", "used", "invalid"]
PENDING: Final = "pending"
EXPIRED: Final = "expired"
USED: Final = "used"
INVALID: Final = "invalid"

_EMPTY_REQUEST_CTX: Final = RequestCtx.empty()


class InviteError(Exception):
    """Base for invite refusals (plain exception, re-raisable through dependencies)."""


class InviteNotFound(InviteError):  # noqa: N818 — reads as a status, maps to 404
    """No live invite with this id (404)."""


class InviteConflict(InviteError):  # noqa: N818 — maps to 409
    """The invite is in a state that refuses the action (409)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True, slots=True, kw_only=True)
class IssuedInvite:
    """An invite plus its plain token; the token is only available here."""

    invite: Invite
    token: str

    def __repr__(self) -> str:
        return f"IssuedInvite(invite_id={self.invite.id})"


def _hash(token: str) -> str:
    return sessions_repo.hash_token(token)


def invite_state(invite: Invite, *, now: datetime) -> InviteLinkState:
    """State of a known invite at ``now``; a revoked invite reads as ``invalid``."""
    if invite.used_at is not None:
        return USED
    if invite.revoked_at is not None:
        return INVALID
    if invite.expires_at <= now:
        return EXPIRED
    return PENDING


def list_invites(conn: sqlite3.Connection) -> list[Invite]:
    """Every live invite, newest first (admin roster)."""
    return invites_repo.list_live(conn)


def _live_invite_or_404(conn: sqlite3.Connection, invite_id: int) -> Invite:
    invite = invites_repo.get_live(conn, invite_id)
    if invite is None:
        raise InviteNotFound(INVITE_NOT_FOUND_MESSAGE)
    return invite


def create_invite(
    conn: sqlite3.Connection,
    actor_user_id: int,
    *,
    email: str,
    is_admin: bool,
    tokens: TokenSource,
    now: datetime,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> IssuedInvite:
    """Invite ``email`` with a role. Refuses a live user's or a pending invite's email.

    Raises :class:`~budget_planner.services.users.UserInputError` (keyed ``email``).
    """
    draft = users_service.build_draft(email=email, name="", is_admin=is_admin)
    token = tokens.new_token(INVITE_TOKEN_BYTES)
    with transaction(conn):
        if users_repo.get_by_email_live(conn, draft.email) is not None:
            raise users_service.UserInputError({"email": users_service.DUPLICATE_EMAIL_MESSAGE})
        if invites_repo.find_pending_for_email(conn, draft.email, now=now) is not None:
            raise users_service.UserInputError({"email": PENDING_INVITE_MESSAGE})
        invite = invites_repo.insert(
            conn,
            email=draft.email,
            is_admin=is_admin,
            invited_by=actor_user_id,
            token_hash=_hash(token),
            created_at=now,
            expires_at=now + INVITE_LIFETIME,
            request_ctx=request_ctx,
        )
    return IssuedInvite(invite=invite, token=token)


def resend_invite(
    conn: sqlite3.Connection,
    actor_user_id: int,
    invite_id: int,
    *,
    tokens: TokenSource,
    now: datetime,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> IssuedInvite:
    """New token and a fresh 7 days; the old token stops working. Refused if used or revoked."""
    token = tokens.new_token(INVITE_TOKEN_BYTES)
    with transaction(conn):
        current = _live_invite_or_404(conn, invite_id)
        if current.used_at is not None or current.revoked_at is not None:
            raise InviteConflict(INVITE_FINAL_MESSAGE)
        invite = invites_repo.rotate_token(
            conn,
            invite_id,
            token_hash=_hash(token),
            expires_at=now + INVITE_LIFETIME,
            now=now,
            actor_user_id=actor_user_id,
            request_ctx=request_ctx,
        )
    return IssuedInvite(invite=invite, token=token)


def revoke_invite(
    conn: sqlite3.Connection,
    actor_user_id: int,
    invite_id: int,
    *,
    now: datetime,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> Invite:
    """Revoke (final). Refused if already used or revoked."""
    with transaction(conn):
        current = _live_invite_or_404(conn, invite_id)
        if current.used_at is not None or current.revoked_at is not None:
            raise InviteConflict(INVITE_FINAL_MESSAGE)
        return invites_repo.mark_revoked(
            conn, invite_id, now=now, actor_user_id=actor_user_id, request_ctx=request_ctx
        )


def _invite_for_token(conn: sqlite3.Connection, token: str) -> Invite | None:
    """Resolve a plain token; re-checks the stored hash in constant time."""
    if not token:
        return None
    digest = _hash(token)
    invite = invites_repo.find_by_token_hash(conn, digest)
    if invite is None or not hmac.compare_digest(invite.token_hash, digest):
        return None
    return invite


def link_state(conn: sqlite3.Connection, token: str, *, now: datetime) -> InviteLinkState:
    """``pending``, ``expired``, ``used`` or ``invalid`` (unknown or revoked) for a link token."""
    invite = _invite_for_token(conn, token)
    return INVALID if invite is None else invite_state(invite, now=now)


def accept_invite(
    conn: sqlite3.Connection,
    token: str,
    *,
    name: str,
    password: str,
    hasher: PasswordHasher,
    now: datetime,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> AuthUser:
    """Create the user (invite's email and role), mark the invite used; one transaction.

    Raises :class:`InviteConflict` unless the link is ``pending``; user input
    errors propagate as :class:`~budget_planner.services.users.UserInputError`
    and roll everything back.
    """
    with transaction(conn):
        invite = _invite_for_token(conn, token)
        if invite is None or invite_state(invite, now=now) != PENDING:
            raise InviteConflict(INVITE_LINK_UNUSABLE_MESSAGE)
        draft = users_service.build_draft(email=invite.email, name=name, is_admin=invite.is_admin)
        user = users_service.create_invited_user(
            conn, draft, password=password, hasher=hasher, request_ctx=request_ctx
        )
        invites_repo.mark_used(
            conn, invite.id, now=now, actor_user_id=user.id, request_ctx=request_ctx
        )
    return user
