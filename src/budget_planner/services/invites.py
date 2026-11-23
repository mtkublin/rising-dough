"""Invites: create, resend, revoke, accept, link state (T-UR30, ADR-0134 section 1 and 10).

An admin invites a person by email and role. The plain token is returned to the
caller once (``IssuedInvite.token``; the mail port of T-UR31 and the copy-link
UI use it) and only ``sha256(token)`` is stored. The token and its hash are
never logged. Clock, entropy, hashing and mail come in as arguments (ADR-0021).

Mail (T-UR31): ``create_invite`` and ``resend_invite`` send the invite email through
the injected :class:`~budget_planner.domain.ports.MailSender` only when the caller
passes ``email_enabled=True`` (``Settings.invite_email_enabled``, default off). The
send runs AFTER the transaction commits: a mail failure (``MailSendError``) is
logged without the token and reported as ``IssuedInvite.mail_sent = False``; the
invite stays valid, so the admin can resend or copy the link. No half-state.
The link is ``<base_url>/invite/<token>``; the caller passes ``base_url`` (the
public origin, e.g. ``Settings.webauthn_origin``); empty gives the path only. The
route is T-UR20's; ``INVITE_LINK_PATH`` is the one place that names it.

Lifecycle: ``pending`` -> ``used`` (accepted) | revoked (final, reads as
``invalid``) | ``expired`` (resend revives it with a new token and expiry).
"""

from __future__ import annotations

import hmac
import logging
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from typing import Final, Literal

from budget_planner.domain.ports import (
    MailMessage,
    MailSender,
    MailSendError,
    PasswordHasher,
    TokenSource,
)
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
INVITE_LINK_PATH: Final = "/invite/"
INVITE_MAIL_SUBJECT: Final = "You are invited to Rising Dough"

logger = logging.getLogger(__name__)

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


class InviteNotFoundError(InviteError):
    """No live invite with this id (404)."""


class InviteConflictError(InviteError):
    """The invite is in a state that refuses the action (409)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True, slots=True, kw_only=True)
class IssuedInvite:
    """An invite plus its plain token; the token is only available here."""

    invite: Invite
    token: str
    mail_sent: bool = False

    def __repr__(self) -> str:
        return f"IssuedInvite(invite_id={self.invite.id})"


def _hash(token: str) -> str:
    return sessions_repo.hash_token(token)


def invite_link(base_url: str, token: str) -> str:
    """``<base_url>/invite/<token>``; the path alone when ``base_url`` is empty."""
    return f"{base_url.rstrip('/')}{INVITE_LINK_PATH}{token}"


def _require_mail(mail: MailSender | None, email_enabled: bool) -> None:
    if email_enabled and mail is None:
        raise ValueError("invite email is enabled but no mail sender was injected")


def _deliver(
    issued: IssuedInvite, *, mail: MailSender | None, email_enabled: bool, base_url: str
) -> IssuedInvite:
    """Send the invite mail after commit; never raises, never logs the token."""
    if not email_enabled or mail is None:
        return issued
    body = (
        "You have been invited to Rising Dough.\n\n"
        f"Open this link to set up your account:\n{invite_link(base_url, issued.token)}\n\n"
        "The link works for 7 days."
    )
    message = MailMessage(to=issued.invite.email, subject=INVITE_MAIL_SUBJECT, body=body)
    try:
        mail.send(message)
    except MailSendError:
        logger.warning("invite mail failed for invite %s", issued.invite.id)
        return issued
    return replace(issued, mail_sent=True)


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
        raise InviteNotFoundError(INVITE_NOT_FOUND_MESSAGE)
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
    mail: MailSender | None = None,
    email_enabled: bool = False,
    base_url: str = "",
) -> IssuedInvite:
    """Invite ``email`` with a role. Refuses a live user's or a pending invite's email.

    Raises :class:`~budget_planner.services.users.UserInputError` (keyed ``email``).
    """
    _require_mail(mail, email_enabled)
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
    return _deliver(
        IssuedInvite(invite=invite, token=token),
        mail=mail,
        email_enabled=email_enabled,
        base_url=base_url,
    )


def resend_invite(
    conn: sqlite3.Connection,
    actor_user_id: int,
    invite_id: int,
    *,
    tokens: TokenSource,
    now: datetime,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
    mail: MailSender | None = None,
    email_enabled: bool = False,
    base_url: str = "",
) -> IssuedInvite:
    """New token and a fresh 7 days; the old token stops working. Refused if used or revoked."""
    _require_mail(mail, email_enabled)
    token = tokens.new_token(INVITE_TOKEN_BYTES)
    with transaction(conn):
        current = _live_invite_or_404(conn, invite_id)
        if current.used_at is not None or current.revoked_at is not None:
            raise InviteConflictError(INVITE_FINAL_MESSAGE)
        invite = invites_repo.rotate_token(
            conn,
            invite_id,
            token_hash=_hash(token),
            expires_at=now + INVITE_LIFETIME,
            now=now,
            actor_user_id=actor_user_id,
            request_ctx=request_ctx,
        )
    return _deliver(
        IssuedInvite(invite=invite, token=token),
        mail=mail,
        email_enabled=email_enabled,
        base_url=base_url,
    )


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
            raise InviteConflictError(INVITE_FINAL_MESSAGE)
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

    Raises :class:`InviteConflictError` unless the link is ``pending``; user input
    errors propagate as :class:`~budget_planner.services.users.UserInputError`
    and roll everything back.
    """
    with transaction(conn):
        invite = _invite_for_token(conn, token)
        if invite is None or invite_state(invite, now=now) != PENDING:
            raise InviteConflictError(INVITE_LINK_UNUSABLE_MESSAGE)
        draft = users_service.build_draft(email=invite.email, name=name, is_admin=invite.is_admin)
        user = users_service.create_invited_user(
            conn, draft, password=password, hasher=hasher, request_ctx=request_ctx
        )
        invites_repo.mark_used(
            conn, invite.id, now=now, actor_user_id=user.id, request_ctx=request_ctx
        )
    return user
