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

from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.services import password_change as password_service
from budget_planner.web.auth_cookies import safe_next
from budget_planner.web.deps import current_user, get_db, get_request_ctx
from budget_planner.web.middleware.auth import CurrentUser
from budget_planner.web.middleware.must_change_password import PASSWORD_PATH
from budget_planner.web.rendering import is_hx_request, render

router = APIRouter(prefix="/settings", tags=["settings"])

_PAGE: Final = "settings/password.html"
_FORM: Final = "settings/_password_form.html"


def _target(next_path: str | None) -> str:
    target = safe_next(next_path)
    return "/" if target.split("?", 1)[0] == PASSWORD_PATH else target


def _render_form(
    request: Request,
    user: CurrentUser,
    *,
    next_path: str,
    outcome: password_service.PasswordChangeOutcome | None = None,
) -> HTMLResponse:
    failed = outcome is not None and not outcome.ok
    return render(
        request,
        _FORM if is_hx_request(request) else _PAGE,
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY if failed else HTTPStatus.OK,
        current_user=user,
        forced=user.must_change_password,
        next_path=next_path,
        outcome=outcome,
        min_length=password_service.MIN_PASSWORD_LENGTH,
    )


@router.get("/password", response_class=HTMLResponse)
def password_form(
    request: Request,
    next_path: str | None = Query(default=None, alias="next"),
    user: CurrentUser = Depends(current_user),
) -> HTMLResponse:
    """Render the change-password form (forced-rotation banner when flagged)."""
    return _render_form(request, user, next_path=_target(next_path))


@router.post("/password", response_model=None)
def change_password(  # noqa: PLR0917
    request: Request,
    current_password: str = Form(default=""),
    new_password: str = Form(default=""),
    confirm_password: str = Form(default=""),
    next_path: str = Form(default="/", alias="next"),
    conn: sqlite3.Connection = Depends(get_db),
    ctx: RequestCtx = Depends(get_request_ctx),
    user: CurrentUser = Depends(current_user),
) -> Response:
    """Rotate the signed-in user's password; other sessions are signed out."""
    target = _target(next_path)
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
        return _render_form(request, user, next_path=target, outcome=outcome)
    if is_hx_request(request):
        return Response(status_code=HTTPStatus.NO_CONTENT, headers={"HX-Redirect": target})
    return RedirectResponse(target, status_code=HTTPStatus.SEE_OTHER)
