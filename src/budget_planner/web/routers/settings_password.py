"""``/settings/password`` — self-service password change (T-D18, ADR-0074).

Thin layer over :mod:`budget_planner.services.password_change`. Works as a
plain HTML form (``303`` to ``next`` on success, ``422`` page on errors) and
under HTMX (the form fragment is swapped on ``422``; success answers with
``HX-Redirect``). Exempt from ``MustChangePasswordMiddleware`` — it is the
only way out of a forced rotation. Rate-limit dependency in
:mod:`budget_planner.web.auth_deps`, response helpers in
:mod:`budget_planner.web.password_flow` (T-Q267).
"""

from __future__ import annotations

import sqlite3
from http import HTTPStatus

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from budget_planner.config import Settings
from budget_planner.domain.ports import PasswordHasher
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.services import password_change as password_service
from budget_planner.services.rate_limit import RateDecision
from budget_planner.web.auth_cookies import DEFAULT_LANDING
from budget_planner.web.auth_deps import password_change_rate_limit, throttled_json
from budget_planner.web.deps import (
    current_user,
    get_db,
    get_password_hasher,
    get_request_ctx,
    get_settings_dep,
)
from budget_planner.web.htmx import wants_json
from budget_planner.web.middleware.auth import CurrentUser
from budget_planner.web.password_flow import (
    attempts_text,
    default_target,
    landing_target,
    render_form,
    success_response,
)
from budget_planner.web.paths import SETTINGS_PATH
from budget_planner.web.rendering import is_hx_request
from budget_planner.web.security_context import PASSWORD_ANCHOR

router = APIRouter(prefix=SETTINGS_PATH, tags=["settings"])


@router.get("/password", response_class=HTMLResponse)
def password_form(
    request: Request,
    next_path: str | None = Query(default=None, alias="next"),
    conn: sqlite3.Connection = Depends(get_db),
    user: CurrentUser = Depends(current_user),
) -> Response:
    """Forced-rotation page; everyone else is sent to Settings -> Security."""
    if not user.must_change_password:
        return RedirectResponse(PASSWORD_ANCHOR, status_code=HTTPStatus.SEE_OTHER)
    return render_form(request, conn, user, next_path=landing_target(next_path))


@router.post("/password", response_model=None)
def change_password(
    request: Request,
    *,
    current_password: str = Form(default=""),
    new_password: str = Form(default=""),
    confirm_password: str = Form(default=""),
    next_path: str = Form(default=DEFAULT_LANDING, alias="next"),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    user: CurrentUser = Depends(current_user),
    hasher: PasswordHasher = Depends(get_password_hasher),
    limit: RateDecision = Depends(password_change_rate_limit),
) -> Response:
    """Rotate the signed-in user's password; other sessions are signed out."""
    target = default_target(user, next_path)
    if not limit.allowed:
        if wants_json(request) and not is_hx_request(request):
            return throttled_json(limit)
        response = render_form(request, conn, user, next_path=target, throttled=True)
        response.headers["Retry-After"] = str(limit.retry_after_seconds)
        return response
    outcome = password_service.change_own_password(
        conn,
        user.id,
        password_service.PasswordChangeRequest(
            current_password=current_password,
            new_password=new_password,
            confirm_password=confirm_password,
        ),
        hasher=hasher,
        current_session_id=getattr(request.state, "session_id", None),
        request_ctx=ctx,
    )
    if not outcome.ok:
        return render_form(
            request,
            conn,
            user,
            next_path=target,
            outcome=outcome,
            attempts=attempts_text(request, conn, settings, user)
            if outcome.message_for("current_password")
            else None,
        )
    return success_response(request, settings, outcome, target)
