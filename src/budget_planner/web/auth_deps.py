"""Auth-route dependencies and response helpers (T-Q267; ADR-0072, ADR-0073, ADR-0142).

Rate-limit dependencies, the admin guard and the JSON/throttle helpers that the auth and
settings routers share. Moved out of ``web/routers`` so routers hold only route handlers.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from datetime import datetime
from http import HTTPStatus
from typing import Annotated, Final

from fastapi import Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.domain.client_ip import UNKNOWN_IP
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.services import rate_limit
from budget_planner.services.rate_limit import RateDecision
from budget_planner.web.deps import (
    client_ip,
    current_user,
    get_db,
    get_request_ctx,
    get_settings_dep,
)
from budget_planner.web.middleware.auth import CurrentUser

RATE_LIMITED: Final = "rate_limited"
RETRY_AFTER: Final = "Retry-After"


def rate_limit_now(request: Request) -> datetime:
    """Current UTC time; tests inject ``app.state.rate_limit_clock``."""
    override: Callable[[], datetime] | None = getattr(request.app.state, "rate_limit_clock", None)
    return override() if override is not None else clock.utc_now()


def ip_identity(request: Request) -> str:
    """Rate-limit identity for the caller's IP."""
    return f"ip={client_ip(request) or UNKNOWN_IP}"


def throttled_json(decision: RateDecision) -> JSONResponse:
    """429 JSON body with ``Retry-After``."""
    return JSONResponse(
        {"error": RATE_LIMITED},
        status_code=HTTPStatus.TOO_MANY_REQUESTS,
        headers={RETRY_AFTER: str(decision.retry_after_seconds)},
    )


def login_rate_limit(
    request: Request,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    ctx: Annotated[RequestCtx, Depends(get_request_ctx)],
    email: Annotated[str, Form()] = "",
) -> RateDecision:
    """Count one password-login attempt per IP+email and per IP."""
    now = rate_limit_now(request)
    ip = ip_identity(request)
    normalised = rate_limit.normalise_email(email)
    decision = rate_limit.combine(
        rate_limit.consume(
            conn,
            rate_limit.SCOPE_LOGIN,
            f"{ip}|email={normalised}",
            rate_limit.login_rules(settings),
            now=now,
        ),
        rate_limit.consume(
            conn, rate_limit.SCOPE_LOGIN_IP, ip, rate_limit.login_ip_rules(settings), now=now
        ),
    )
    if not decision.allowed:
        rate_limit.audit_throttled(conn, ctx, scope=decision.scope, email=normalised or None)
    return decision


def passkey_login_rate_limit(
    request: Request,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    ctx: Annotated[RequestCtx, Depends(get_request_ctx)],
) -> RateDecision:
    """Count one passkey-login finish per IP."""
    decision = rate_limit.consume(
        conn,
        rate_limit.SCOPE_PASSKEY_LOGIN,
        ip_identity(request),
        rate_limit.passkey_login_rules(settings),
        now=rate_limit_now(request),
    )
    if not decision.allowed:
        rate_limit.audit_throttled(conn, ctx, scope=decision.scope)
    return decision


def _user_scoped_limit(
    request: Request,
    conn: sqlite3.Connection,
    ctx: RequestCtx,
    user: CurrentUser,
    *,
    scope: str,
    rules: Sequence[rate_limit.RateRule],
) -> RateDecision:
    decision = rate_limit.consume(
        conn, scope, rate_limit.user_identity(user.id), rules, now=rate_limit_now(request)
    )
    if not decision.allowed:
        rate_limit.audit_throttled(conn, ctx, scope=decision.scope, user_id=user.id)
    return decision


def register_rate_limit(
    request: Request,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    ctx: Annotated[RequestCtx, Depends(get_request_ctx)],
    user: Annotated[CurrentUser, Depends(current_user)],
) -> RateDecision:
    """Count one passkey-registration finish per signed-in user."""
    return _user_scoped_limit(
        request,
        conn,
        ctx,
        user,
        scope=rate_limit.SCOPE_REGISTER,
        rules=rate_limit.register_rules(settings),
    )


def reauth_rate_limit(
    request: Request,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    ctx: Annotated[RequestCtx, Depends(get_request_ctx)],
    user: Annotated[CurrentUser, Depends(current_user)],
) -> RateDecision:
    """Count one re-auth attempt per signed-in user (T-D53b, ADR-0076 section 2)."""
    return _user_scoped_limit(
        request,
        conn,
        ctx,
        user,
        scope=rate_limit.SCOPE_REAUTH,
        rules=rate_limit.reauth_rules(settings),
    )


def password_change_rate_limit(
    request: Request,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    ctx: Annotated[RequestCtx, Depends(get_request_ctx)],
    user: Annotated[CurrentUser, Depends(current_user)],
) -> RateDecision:
    """Count one password-change attempt per signed-in user (T-D18a, ADR-0072)."""
    return _user_scoped_limit(
        request,
        conn,
        ctx,
        user,
        scope=rate_limit.SCOPE_PASSWORD_CHANGE,
        rules=rate_limit.password_change_rules(settings),
    )


def current_admin(request: Request) -> CurrentUser:
    """Return the session admin; 404 (never 403) for anyone else (ADR-0073 section 1).

    Second layer behind ``AdminRequiredMiddleware``, which normally answers first.
    """
    user = current_user(request)
    if not user.is_admin:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)
    return user
