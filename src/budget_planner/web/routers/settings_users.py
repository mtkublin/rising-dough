"""Admin-only user roster at ``/settings/users`` (T-D17, ADR-0061 §4, ADR-0073).

Thin layer over :mod:`budget_planner.services.users`. ``AdminRequiredMiddleware``
already answers 404 to non-admins. The :func:`current_admin` dependency
repeats that check in case the router is ever mounted without it.

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
from typing import Any, Final

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories.auth_users import AuthUser
from budget_planner.services import users as users_service
from budget_planner.services.users import UserConflict, UserInputError, UserNotFound
from budget_planner.web.deps import current_user, get_db, get_request_ctx
from budget_planner.web.middleware.auth import CurrentUser
from budget_planner.web.rendering import is_hx_request, render

LIST_PATH: Final = "/settings/users"
_LIST_TEMPLATE: Final = "settings/users/list.html"
_TABLE_TEMPLATE: Final = "settings/users/_table.html"
_TOAST_TEMPLATE: Final = "settings/users/_password-toast.html"
_ADD_ERRORS_TEMPLATE: Final = "settings/users/_add-errors.html"
_EDIT_TEMPLATE: Final = "settings/users/edit.html"
_SLIDEOVER_TEMPLATE: Final = "partials/_slideover.html"
_FLASH_TEMPLATE: Final = "partials/_flash.html"
_NOT_FOUND_TEMPLATE: Final = "errors/404.html"
_CONFLICT_TEMPLATE: Final = "errors/409.html"

router = APIRouter(prefix=LIST_PATH, tags=["settings-users"])


def current_admin(request: Request) -> CurrentUser:
    """Return the session admin; 404 (never 403) for anyone else (ADR-0073 §1).

    Second layer behind ``AdminRequiredMiddleware``, which normally answers first.
    """
    user = current_user(request)
    if not user.is_admin:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)
    return user


def _not_found(request: Request) -> HTMLResponse:
    """The app's standard 404 (full page, or an error flash for HTMX)."""
    if is_hx_request(request):
        return render(
            request,
            _FLASH_TEMPLATE,
            HTTPStatus.NOT_FOUND,
            level="error",
            message="User not found",
        )
    return render(request, _NOT_FOUND_TEMPLATE, HTTPStatus.NOT_FOUND, entity="user", entity_id=0)


def _checkbox(value: str | None) -> bool:
    return value is not None and value.lower() in {"on", "1", "true", "yes"}


def _no_store(response: HTMLResponse) -> HTMLResponse:
    response.headers["Cache-Control"] = "no-store"
    return response


def _see_other() -> RedirectResponse:
    return RedirectResponse(LIST_PATH, status_code=HTTPStatus.SEE_OTHER)


def _page_context(conn: sqlite3.Connection, admin: CurrentUser) -> dict[str, Any]:
    return {
        "active_tab": "users",
        "users": users_service.list_live_users(conn),
        "me_id": admin.id,
        "form_errors": {},
        "form_values": {},
        "toast": None,
    }


def _toast(user: AuthUser, password: str, *, kind: str) -> dict[str, Any]:
    return {"kind": kind, "email": user.email or user.name, "password": password}


def _render_toast(
    request: Request, conn: sqlite3.Connection, admin: CurrentUser, toast: dict[str, Any]
) -> HTMLResponse:
    """Toast in ``#user-feedback`` (HTMX) or the full page with it inline."""
    context = {**_page_context(conn, admin), "toast": toast}
    hx = is_hx_request(request)
    template = _TOAST_TEMPLATE if hx else _LIST_TEMPLATE
    return _no_store(render(request, template, oob_table=hx, **context))


def _conflict(request: Request, exc: UserConflict) -> HTMLResponse:
    """409: error flash with ``HX-Reswap: none`` (HTMX) or the 409 page."""
    if not is_hx_request(request):
        return render(request, _CONFLICT_TEMPLATE, HTTPStatus.CONFLICT, message=exc.message)
    response = render(
        request, _FLASH_TEMPLATE, HTTPStatus.CONFLICT, level="error", message=exc.message
    )
    response.headers["HX-Reswap"] = "none"
    return response


def _table_with_flash(
    request: Request, conn: sqlite3.Connection, admin: CurrentUser, message: str
) -> HTMLResponse:
    return render(
        request,
        _TABLE_TEMPLATE,
        users=users_service.list_live_users(conn),
        me_id=admin.id,
        flash_message=message,
    )


@router.get("", response_class=HTMLResponse)
def list_users(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
) -> HTMLResponse:
    """Roster page: every live user with Edit / Reset password / Remove."""
    return render(request, _LIST_TEMPLATE, **_page_context(conn, admin))


@router.post("", response_class=HTMLResponse)
def create_user(
    request: Request,
    *,
    email: str = Form(default=""),
    name: str = Form(default=""),
    is_admin: str | None = Form(default=None),
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
    request_ctx: RequestCtx = Depends(get_request_ctx),
) -> HTMLResponse:
    """Create a user; show the generated password once."""
    try:
        draft = users_service.build_draft(email=email, name=name, is_admin=_checkbox(is_admin))
        user, password = users_service.create_user(conn, admin.id, draft, request_ctx=request_ctx)
    except UserInputError as exc:
        if is_hx_request(request):
            return render(
                request, _ADD_ERRORS_TEMPLATE, HTTPStatus.UNPROCESSABLE_ENTITY, errors=exc.fields
            )
        context = {
            **_page_context(conn, admin),
            "form_errors": exc.fields,
            "form_values": {"email": email, "name": name, "is_admin": _checkbox(is_admin)},
        }
        return render(request, _LIST_TEMPLATE, HTTPStatus.UNPROCESSABLE_ENTITY, **context)
    return _render_toast(request, conn, admin, _toast(user, password, kind="created"))


def _edit_response(
    request: Request,
    user: AuthUser,
    *,
    me_id: int,
    errors: dict[str, str],
    values: dict[str, Any] | None = None,
    status: int = HTTPStatus.OK,
) -> HTMLResponse:
    form_values = values or {
        "email": user.email or "",
        "name": user.name,
        "is_admin": user.is_admin,
    }
    context: dict[str, Any] = {
        "target": user,
        "me_id": me_id,
        "errors": errors,
        "form_values": form_values,
        "hx_enabled": is_hx_request(request),
    }
    if is_hx_request(request) and errors:
        response = render(request, _EDIT_TEMPLATE, status, **context)
        response.headers["HX-Retarget"] = "#user-edit-form"
        response.headers["HX-Reswap"] = "outerHTML"
        return response
    return render(
        request,
        _SLIDEOVER_TEMPLATE,
        status,
        slide_over_title=f"Edit {user.email or user.name}",
        form_include=_EDIT_TEMPLATE,
        **context,
    )


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
        return _not_found(request)
    return _edit_response(request, user, me_id=admin.id, errors={})


@router.post("/{user_id}", response_model=None)
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
        return _not_found(request)
    values = {"email": email, "name": name, "is_admin": _checkbox(is_admin)}
    try:
        draft = users_service.build_draft(email=email, name=name, is_admin=_checkbox(is_admin))
        updated = users_service.edit_user(conn, admin.id, user_id, draft, request_ctx=request_ctx)
    except UserInputError as exc:
        return _edit_response(
            request,
            target,
            me_id=admin.id,
            errors=exc.fields,
            values=values,
            status=HTTPStatus.UNPROCESSABLE_ENTITY,
        )
    except UserConflict as exc:
        return _conflict(request, exc)
    except UserNotFound:
        return _not_found(request)
    if not is_hx_request(request):
        return _see_other()
    return _table_with_flash(request, conn, admin, f"Saved {updated.email or updated.name}.")


@router.post("/{user_id}/reset-password", response_class=HTMLResponse)
def reset_password(
    request: Request,
    user_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
    request_ctx: RequestCtx = Depends(get_request_ctx),
) -> HTMLResponse:
    """Generate a new one-shot password and revoke the target's sessions."""
    try:
        user, password = users_service.reset_password(
            conn, admin.id, user_id, request_ctx=request_ctx
        )
    except UserNotFound:
        return _not_found(request)
    return _render_toast(request, conn, admin, _toast(user, password, kind="reset"))


@router.post("/{user_id}/delete", response_model=None)
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
        return _conflict(request, exc)
    except UserNotFound:
        return _not_found(request)
    if not is_hx_request(request):
        return _see_other()
    return _table_with_flash(request, conn, admin, f"Removed {removed.email or removed.name}.")
