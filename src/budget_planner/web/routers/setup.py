"""First-run setup ``/setup`` (T-UR21) and invite landing ``/invite/{token}`` (T-UR20a).

ADR-0134 sections 1 and 9, ADR-0148. The invite landing is public (``AuthRequiredMiddleware``
exempts the ``/invite/`` prefix); its POSTs share the login-IP rate limit below.

Thin layer over :mod:`budget_planner.services.setup`. Reachable without a session
(``AuthRequiredMiddleware`` exempts ``/setup``). While setup is closed (a user
exists, token consumed, bootstrap admin configured, or no hash configured) the
page redirects to sign in; while it is open, a missing or wrong token is a bare
404 (no oracle). The token is carried in a hidden field, never logged, never
echoed anywhere but back into that field. POST attempts are counted per IP in
the login-IP bucket before the token is checked (ADR-0072).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from http import HTTPStatus

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response

from budget_planner.config import Settings
from budget_planner.domain.ports import PasswordHasher
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.services import (
    auth as auth_service,
    invites as invites_service,
    setup as setup_service,
)
from budget_planner.services.rate_limit import RateDecision
from budget_planner.services.users import UserInputError
from budget_planner.web.auth_cookies import DEFAULT_LANDING, LOGIN_PATH
from budget_planner.web.auth_flow import redirect, start_session
from budget_planner.web.deps import (
    client_ip,
    get_db,
    get_password_hasher,
    get_request_ctx,
    get_settings_dep,
    reauth_now,
    request_user_agent,
)
from budget_planner.web.invite_flow import invite_page, refused_invite, throttled_invite
from budget_planner.web.setup_flow import setup_page, setup_rate_limit, throttled_setup

router = APIRouter(tags=["setup"])


@router.get("/setup", response_class=HTMLResponse, response_model=None)
def setup_form(
    request: Request,
    token: str = Query(default=""),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> Response:
    """The first-admin form; sign-in redirect when closed, 404 without a valid token."""
    if not setup_service.is_open(conn, settings):
        return redirect(LOGIN_PATH)
    if not setup_service.check_token(conn, settings, token):
        raise HTTPException(HTTPStatus.NOT_FOUND)
    return setup_page(request, token=token)


@router.post("/setup", response_model=None)
def setup_submit(
    request: Request,
    *,
    token: str = Form(default=""),
    name: str = Form(default=""),
    email: str = Form(default=""),
    password: str = Form(default=""),
    password_confirm: str = Form(default=""),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    hasher: PasswordHasher = Depends(get_password_hasher),
    limit: RateDecision = Depends(setup_rate_limit),
) -> Response:
    """Create the first admin, sign them in, land on Today."""
    if not limit.allowed:
        return throttled_setup(request, limit, token=token, name=name, email=email)
    if not setup_service.is_open(conn, settings):
        return redirect(LOGIN_PATH)
    draft = setup_service.SetupDraft(
        email=email, name=name, password=password, password_confirm=password_confirm
    )
    try:
        admin = setup_service.complete_setup(
            conn, settings, token=token, draft=draft, hasher=hasher, request_ctx=ctx
        )
    except setup_service.SetupClosedError as exc:
        raise HTTPException(HTTPStatus.NOT_FOUND) from exc
    except UserInputError as exc:
        return setup_page(
            request,
            token=token,
            name=name,
            email=email,
            errors=dict(exc.fields),
            status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    session = auth_service.authenticate_password(
        conn,
        admin.email or email,
        password,
        ip=client_ip(request),
        user_agent=request_user_agent(request),
        hasher=hasher,
        request_ctx=ctx,
    )
    if session is None:  # pragma: no cover - the admin was created a moment ago
        return redirect(LOGIN_PATH)
    return start_session(request, conn, settings, session, redirect(DEFAULT_LANDING))


@router.get("/invite/{token}", response_class=HTMLResponse)
def invite_form(
    request: Request,
    token: str,
    conn: sqlite3.Connection = Depends(get_db),
    now: datetime = Depends(reauth_now),
) -> HTMLResponse:
    """Invite landing (T-UR20a): the accept form for a pending link, the state page otherwise."""
    state, invite = invites_service.link_invite(conn, token, now=now)
    return invite_page(request, conn, token, state, invite)


@router.post("/invite/{token}", response_model=None)
def invite_accept(
    request: Request,
    token: str,
    *,
    name: str = Form(default=""),
    password: str = Form(default=""),
    password_confirm: str = Form(default=""),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    hasher: PasswordHasher = Depends(get_password_hasher),
    now: datetime = Depends(reauth_now),
    limit: RateDecision = Depends(setup_rate_limit),
) -> Response:
    """Create the account of an invite, sign in, land on Today (ADR-0134 section 1)."""
    if not limit.allowed:
        return throttled_invite(request, conn, token, limit, name=name, now=now)
    try:
        user = invites_service.accept_invite(
            conn,
            token,
            name=name,
            password=password,
            password_confirm=password_confirm,
            hasher=hasher,
            now=now,
            request_ctx=ctx,
        )
    except (invites_service.InviteConflictError, UserInputError) as exc:
        return refused_invite(request, conn, token, exc, name=name, now=now)
    session = auth_service.authenticate_password(
        conn,
        user.email or "",
        password,
        ip=client_ip(request),
        user_agent=request_user_agent(request),
        hasher=hasher,
        request_ctx=ctx,
    )
    if session is None:
        return redirect(LOGIN_PATH)
    return start_session(request, conn, settings, session, redirect(DEFAULT_LANDING))
