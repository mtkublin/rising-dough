"""Admin-only user roster at ``/settings/users`` (T-D17, ADR-0061 §4, ADR-0073).

Thin layer over :mod:`budget_planner.services.users`. ``AdminRequiredMiddleware``
already answers 404 to non-admins. The :func:`~budget_planner.web.auth_deps.current_admin`
dependency repeats that check in case the router is ever mounted without it.
Renderers live in :mod:`budget_planner.web.users_admin` (T-Q267).

HTMX contract (``static/js/users-admin.js`` + ``templates/settings/users/*``):

- Add / reset swap the one-shot password toast into ``#user-feedback`` and
  re-render ``#users-table`` out of band. The response is ``no-store``.
- Edit / remove re-render ``#users-table`` (``outerHTML``) and flash a
  success message out of band.
- 422 (invalid / duplicate email) re-renders the add errors, or the edit
  form via ``HX-Retarget``. 409 (last admin / self-removal) is a flash with
  ``HX-Reswap: none``.

Non-HTMX fallbacks: add / reset re-render the full page with the toast (no
redirect, so the password is not lost); edit / remove redirect 303 back
to the list.
"""

from __future__ import annotations

import sqlite3
from http import HTTPStatus

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget_planner.domain.ports import TokenSource
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.services import users as users_service
from budget_planner.services.users import UserConflict, UserInputError, UserNotFound
from budget_planner.web.auth_deps import current_admin
from budget_planner.web.deps import get_db, get_request_ctx, get_token_source, require_recent_auth
from budget_planner.web.middleware.auth import CurrentUser
from budget_planner.web.rendering import is_hx_request, render, render_context
from budget_planner.web.users_admin import (
    ADD_ERRORS_TEMPLATE,
    LIST_PATH,
    LIST_TEMPLATE,
    checkbox,
    conflict,
    edit_response,
    not_found,
    page_context,
    password_toast,
    render_toast,
    see_other,
    table_with_flash,
)

router = APIRouter(prefix=LIST_PATH, tags=["settings-users"])


@router.get("", response_class=HTMLResponse)
def list_users(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
) -> HTMLResponse:
    """Roster page: every live user with Edit / Reset password / Remove."""
    return render_context(request, LIST_TEMPLATE, page_context(conn, admin))


@router.post("", response_class=HTMLResponse, dependencies=[Depends(require_recent_auth)])
def create_user(
    request: Request,
    *,
    email: str = Form(default=""),
    name: str = Form(default=""),
    is_admin: str | None = Form(default=None),
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
    request_ctx: RequestCtx = Depends(get_request_ctx),
    tokens: TokenSource = Depends(get_token_source),
) -> HTMLResponse:
    """Create a user; show the generated password once."""
    try:
        draft = users_service.build_draft(email=email, name=name, is_admin=checkbox(is_admin))
        user, password = users_service.create_user(
            conn, admin.id, draft, tokens=tokens, request_ctx=request_ctx
        )
    except UserInputError as exc:
        if is_hx_request(request):
            return render(
                request, ADD_ERRORS_TEMPLATE, HTTPStatus.UNPROCESSABLE_ENTITY, errors=exc.fields
            )
        context = {
            **page_context(conn, admin),
            "form_errors": exc.fields,
            "form_values": {"email": email, "name": name, "is_admin": checkbox(is_admin)},
        }
        return render(request, LIST_TEMPLATE, HTTPStatus.UNPROCESSABLE_ENTITY, **context)
    return render_toast(request, conn, admin, password_toast(user, password, kind="created"))


@router.get("/{user_id}/edit", response_class=HTMLResponse)
def edit_form(
    request: Request,
    user_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
) -> HTMLResponse:
    """Edit slide-over (email, name, admin toggle)."""
    try:
        user = users_service.get_live_user(conn, user_id)
    except UserNotFound:
        return not_found(request)
    return edit_response(request, user, me_id=admin.id, errors={})


@router.post("/{user_id}", response_model=None, dependencies=[Depends(require_recent_auth)])
def save_user(
    request: Request,
    user_id: int,
    *,
    email: str = Form(default=""),
    name: str = Form(default=""),
    is_admin: str | None = Form(default=None),
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
    request_ctx: RequestCtx = Depends(get_request_ctx),
) -> Response:
    """Save edits; enforce live-email uniqueness and the last-admin rule."""
    try:
        target = users_service.get_live_user(conn, user_id)
    except UserNotFound:
        return not_found(request)
    # A missing field means "unchanged" (Q-063); the edit form always sends it.
    admin_flag = None if is_admin is None else checkbox(is_admin)
    values = {
        "email": email,
        "name": name,
        "is_admin": target.is_admin if admin_flag is None else admin_flag,
    }
    try:
        draft = users_service.build_draft(email=email, name=name, is_admin=admin_flag)
        updated = users_service.edit_user(conn, admin.id, user_id, draft, request_ctx=request_ctx)
    except UserInputError as exc:
        return edit_response(
            request,
            target,
            me_id=admin.id,
            errors=exc.fields,
            values=values,
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    except UserConflict as exc:
        return conflict(request, exc)
    except UserNotFound:
        return not_found(request)
    if not is_hx_request(request):
        return see_other()
    return table_with_flash(request, conn, admin, f"Saved {updated.email or updated.name}.")


@router.post(
    "/{user_id}/reset-password",
    response_class=HTMLResponse,
    dependencies=[Depends(require_recent_auth)],
)
def reset_password(
    request: Request,
    user_id: int,
    *,
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
    request_ctx: RequestCtx = Depends(get_request_ctx),
    tokens: TokenSource = Depends(get_token_source),
) -> HTMLResponse:
    """Generate a new one-shot password and revoke the target's sessions."""
    try:
        user, password = users_service.reset_password(
            conn, admin.id, user_id, tokens=tokens, request_ctx=request_ctx
        )
    except UserNotFound:
        return not_found(request)
    return render_toast(request, conn, admin, password_toast(user, password, kind="reset"))


@router.post("/{user_id}/delete", response_model=None, dependencies=[Depends(require_recent_auth)])
def delete_user(
    request: Request,
    user_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
    request_ctx: RequestCtx = Depends(get_request_ctx),
) -> Response:
    """Soft-delete a user and revoke all their sessions (one transaction)."""
    try:
        removed = users_service.soft_delete_user(conn, admin.id, user_id, request_ctx=request_ctx)
    except UserConflict as exc:
        return conflict(request, exc)
    except UserNotFound:
        return not_found(request)
    if not is_hx_request(request):
        return see_other()
    return table_with_flash(request, conn, admin, f"Removed {removed.email or removed.name}.")
