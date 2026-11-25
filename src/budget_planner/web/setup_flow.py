"""Helpers for the first-run ``/setup`` routes (T-UR21; ADR-0134 section 9, ADR-0072).

The rate-limit dependency and the page renderer live here so
:mod:`budget_planner.web.routers.setup` only holds route handlers.
"""

from __future__ import annotations

import sqlite3
from http import HTTPStatus
from typing import Annotated, Final

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse

from budget_planner.config import Settings
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.services import rate_limit
from budget_planner.services.rate_limit import RateDecision
from budget_planner.web.auth_deps import RETRY_AFTER, ip_identity, rate_limit_now
from budget_planner.web.auth_flow import RATE_LIMITED_LOGIN_ERROR
from budget_planner.web.deps import get_db, get_request_ctx, get_settings_dep
from budget_planner.web.rendering import render

SETUP_TEMPLATE: Final = "pages/auth/setup.html"


def setup_rate_limit(
    request: Request,
    conn: Annotated[sqlite3.Connection, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    ctx: Annotated[RequestCtx, Depends(get_request_ctx)],
) -> RateDecision:
    """Count one setup attempt per IP (shares the login-IP backstop, ADR-0072)."""
    decision = rate_limit.consume(
        conn,
        rate_limit.SCOPE_LOGIN_IP,
        ip_identity(request),
        rate_limit.login_ip_rules(settings),
        now=rate_limit_now(request),
    )
    if not decision.allowed:
        rate_limit.audit_throttled(conn, ctx, scope=decision.scope)
    return decision


def setup_page(
    request: Request,
    *,
    token: str,
    name: str = "",
    email: str = "",
    errors: dict[str, str] | None = None,
    alert: str | None = None,
    status_code: int = HTTPStatus.OK,
) -> HTMLResponse:
    """The setup form; the token rides in a hidden field, passwords are never echoed."""
    return render(
        request,
        SETUP_TEMPLATE,
        status_code=status_code,
        token=token,
        name=name,
        email=email,
        errors=errors or {},
        alert=alert,
    )


def throttled_setup(
    request: Request, decision: RateDecision, *, token: str, name: str, email: str
) -> HTMLResponse:
    """429 page with ``Retry-After`` for a throttled setup attempt."""
    page = setup_page(
        request,
        token=token,
        name=name,
        email=email,
        alert=RATE_LIMITED_LOGIN_ERROR,
        status_code=HTTPStatus.TOO_MANY_REQUESTS,
    )
    page.headers[RETRY_AFTER] = str(decision.retry_after_seconds)
    return page
