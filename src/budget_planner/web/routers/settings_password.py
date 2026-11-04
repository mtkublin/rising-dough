"""``/settings/password`` — self-service password change (T-D18, ADR-0074).

Thin layer over :mod:`budget_planner.services.password_change`. Works as a
plain HTML form (``303`` to ``next`` on success, ``422`` page on errors) and
under HTMX (the form fragment is swapped on ``422``; success answers with
``HX-Redirect``). Exempt from ``MustChangePasswordMiddleware`` — it is the
only way out of a forced rotation.
"""

from __future__ import annotations

import sqlite3
from http import HTTPStatus
from typing import Final

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from budget_planner.config import Settings
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.services import password_change as password_service, rate_limit
from budget_planner.services.rate_limit import RateDecision
from budget_planner.web.auth_cookies import DEFAULT_LANDING, safe_next
from budget_planner.web.deps import current_user, get_db, get_request_ctx, get_settings_dep
from budget_planner.web.middleware.auth import CurrentUser
from budget_planner.web.middleware.must_change_password import PASSWORD_PATH
from budget_planner.web.rendering import is_hx_request, render
from budget_planner.web.routers.auth import _rate_limit_now, _throttled_json, _wants_json
from budget_planner.web.routers.settings_security import (
    PASSWORD_ANCHOR,
    SECURITY_PATH,
    security_context,
)

router = APIRouter(prefix="/settings", tags=["settings"])

_PAGE: Final = "settings/password.html"
_FORM: Final = "settings/_password_form.html"
_SECURITY_PAGE: Final = "settings/security.html"
THROTTLED_FORM_ERROR: Final = "Too many attempts. Please wait a few minutes and try again."


def password_change_rate_limit(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    ctx: RequestCtx = Depends(get_request_ctx),
    user: CurrentUser = Depends(current_user),
) -> RateDecision:
    """Count one password-change attempt per signed-in user (T-D18a, ADR-0072)."""
    decision = rate_limit.consume(
        conn,
        rate_limit.SCOPE_PASSWORD_CHANGE,
        f"user={user.id}",
        rate_limit.password_change_rules(settings),
        now=_rate_limit_now(request),
    )
    if not decision.allowed:
        rate_limit.audit_throttled(conn, ctx, scope=decision.scope, user_id=user.id)
    return decision


def _target(next_path: str | None) -> str:
    target = safe_next(next_path)
    return DEFAULT_LANDING if target.split("?", 1)[0] == PASSWORD_PATH else target


def _default_target(user: CurrentUser, next_path: str | None) -> str:
    """Forced users go on to ``next``; others stay in Settings -> Security."""
    if user.must_change_password:
        return _target(next_path)
    target = _target(next_path)
    return SECURITY_PATH if target == DEFAULT_LANDING else target


def _render_form(
    request: Request,
    conn: sqlite3.Connection,
    user: CurrentUser,
    *,
    next_path: str,
    outcome: password_service.PasswordChangeOutcome | None = None,
    throttled: bool = False,
) -> HTMLResponse:
    failed = outcome is not None and not outcome.ok
    status = HTTPStatus.UNPROCESSABLE_ENTITY if failed else HTTPStatus.OK
    context = {
        "current_user": user,
        "forced": user.must_change_password,
        "next_path": next_path,
        "outcome": outcome,
        "min_length": password_service.MIN_PASSWORD_LENGTH,
        "throttle_error": THROTTLED_FORM_ERROR if throttled else None,
    }
    if not user.must_change_password and not is_hx_request(request):
        context = {**security_context(request, conn, user), **context}
        page = _SECURITY_PAGE
    else:
        page = _FORM if is_hx_request(request) else _PAGE
    return render(
        request,
        page,
        status_code=HTTPStatus.TOO_MANY_REQUESTS if throttled else status,
        **context,
    )


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
    return _render_form(request, conn, user, next_path=_target(next_path))


@router.post("/password", response_model=None)
def change_password(  # noqa: PLR0917
    request: Request,
    current_password: str = Form(default=""),
    new_password: str = Form(default=""),
    confirm_password: str = Form(default=""),
    next_path: str = Form(default=DEFAULT_LANDING, alias="next"),
    conn: sqlite3.Connection = Depends(get_db),
    ctx: RequestCtx = Depends(get_request_ctx),
    user: CurrentUser = Depends(current_user),
    limit: RateDecision = Depends(password_change_rate_limit),
) -> Response:
    """Rotate the signed-in user's password; other sessions are signed out."""
    target = _default_target(user, next_path)
    if not limit.allowed:
        if _wants_json(request) and not is_hx_request(request):
            return _throttled_json(limit)
        response = _render_form(request, conn, user, next_path=target, throttled=True)
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
        current_session_id=getattr(request.state, "session_id", None),
        request_ctx=ctx,
    )
    if not outcome.ok:
        return _render_form(request, conn, user, next_path=target, outcome=outcome)
    if is_hx_request(request):
        return Response(status_code=HTTPStatus.NO_CONTENT, headers={"HX-Redirect": target})
    return RedirectResponse(target, status_code=HTTPStatus.SEE_OTHER)
