"""Helpers for the public invite landing routes (T-UR20a; ADR-0134 section 1, ADR-0148).

The renderer and the state texts live here so :mod:`budget_planner.web.routers.invite`
only holds route handlers. The token rides in the path (never logged, never echoed
beyond the form action).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from http import HTTPStatus
from types import MappingProxyType
from typing import Final

from fastapi import Request
from fastapi.responses import HTMLResponse

from budget_planner.repositories.invites import Invite
from budget_planner.services import invites as invites_service, users as users_service
from budget_planner.services.invites import EXPIRED, INVALID, PENDING, USED, InviteLinkState
from budget_planner.services.rate_limit import RateDecision
from budget_planner.web.auth_deps import RETRY_AFTER
from budget_planner.web.auth_flow import RATE_LIMITED_LOGIN_ERROR
from budget_planner.web.middleware.asgi import CACHE_CONTROL_HEADER, NO_STORE
from budget_planner.web.rendering import render

INVITE_TEMPLATE: Final = "pages/auth/invite.html"
INVITE_PATH: Final = "/invite"
STATE_MESSAGES: Final = MappingProxyType(
    {
        EXPIRED: "This invite link has expired. Ask an admin to resend it.",
        USED: "This invite has already been used. Sign in with the account it created.",
        INVALID: "This link isn\u2019t valid. Ask an admin to resend the invite.",
    }
)


def _inviter_email(conn: sqlite3.Connection, invite: Invite) -> str:
    """Email of the admin who invited (empty when that account is gone)."""
    for user in users_service.list_live_users(conn):
        if user.id == invite.invited_by:
            return user.email or ""
    return ""


def invite_page(
    request: Request,
    conn: sqlite3.Connection,
    token: str,
    state: InviteLinkState,
    invite: Invite | None,
    *,
    name: str = "",
    errors: dict[str, str] | None = None,
    alert: str | None = None,
    status_code: int = HTTPStatus.OK,
) -> HTMLResponse:
    """The accept form for a pending link, or the state page (expired, used, invalid)."""
    form = state == PENDING and invite is not None
    response = render(
        request,
        INVITE_TEMPLATE,
        status_code=status_code,
        token=token,
        pending=form,
        email=invite.email if invite is not None and form else "",
        invited_by=_inviter_email(conn, invite) if invite is not None and form else "",
        name=name,
        errors=errors or {},
        alert=alert if alert else STATE_MESSAGES.get(state, ""),
    )
    response.headers[CACHE_CONTROL_HEADER] = NO_STORE  # the page and its URL carry a secret
    return response


def throttled_invite(
    request: Request,
    conn: sqlite3.Connection,
    token: str,
    decision: RateDecision,
    *,
    name: str,
    now: datetime,
) -> HTMLResponse:
    """429 page with ``Retry-After`` for a throttled accept attempt."""
    state, invite = invites_service.link_invite(conn, token, now=now)
    page = invite_page(
        request,
        conn,
        token,
        state,
        invite,
        name=name,
        alert=RATE_LIMITED_LOGIN_ERROR,
        status_code=HTTPStatus.TOO_MANY_REQUESTS,
    )
    page.headers[RETRY_AFTER] = str(decision.retry_after_seconds)
    return page


def refused_invite(
    request: Request,
    conn: sqlite3.Connection,
    token: str,
    exc: invites_service.InviteConflictError | users_service.UserInputError,
    *,
    name: str,
    now: datetime,
) -> HTMLResponse:
    """A refused accept: 422 with field errors, or the state page if the link stopped working."""
    state, invite = invites_service.link_invite(conn, token, now=now)
    fields = exc.fields if isinstance(exc, users_service.UserInputError) else {}
    return invite_page(
        request,
        conn,
        token,
        state,
        invite,
        name=name,
        errors=dict(fields),
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY if fields else HTTPStatus.OK,
    )


__all__ = [
    "INVITE_PATH",
    "INVITE_TEMPLATE",
    "STATE_MESSAGES",
    "invite_page",
    "refused_invite",
    "throttled_invite",
]
