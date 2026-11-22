"""Response helpers for the admin user roster (T-Q267; T-D17, ADR-0061 section 4, ADR-0073).

Renderers for the roster page, the one-shot password toast, the edit slide-over and the
404/409 flashes, moved out of ``web/routers/settings_users.py``.
"""

from __future__ import annotations

import sqlite3
from http import HTTPStatus
from typing import Final

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from budget_planner.services import users as users_service
from budget_planner.services.users import AuthUser, UserConflict
from budget_planner.web.middleware.auth import CurrentUser
from budget_planner.web.rendering import is_hx_request, render, render_context

LIST_PATH: Final = "/settings/users"
LIST_TEMPLATE: Final = "settings/users/list.html"
TABLE_TEMPLATE: Final = "settings/users/_table.html"
TOAST_TEMPLATE: Final = "settings/users/_password-toast.html"
ADD_ERRORS_TEMPLATE: Final = "settings/users/_add-errors.html"
EDIT_TEMPLATE: Final = "settings/users/edit.html"
SLIDEOVER_TEMPLATE: Final = "partials/_slideover.html"
FLASH_TEMPLATE: Final = "partials/_flash.html"
NOT_FOUND_TEMPLATE: Final = "errors/404.html"
CONFLICT_TEMPLATE: Final = "errors/409.html"
_CHECKBOX_TRUE: Final = frozenset({"on", "1", "true", "yes"})


def checkbox(value: str | None) -> bool:
    """HTML checkbox text to a bool (absent means unchecked)."""
    return value is not None and value.lower() in _CHECKBOX_TRUE


def not_found(request: Request) -> HTMLResponse:
    """The app's standard 404 (full page, or an error flash for HTMX)."""
    if is_hx_request(request):
        return render(
            request,
            FLASH_TEMPLATE,
            HTTPStatus.NOT_FOUND,
            level="error",
            message="User not found",
        )
    return render(request, NOT_FOUND_TEMPLATE, HTTPStatus.NOT_FOUND, entity="user", entity_id=0)


def see_other() -> RedirectResponse:
    """303 back to the roster."""
    return RedirectResponse(LIST_PATH, status_code=HTTPStatus.SEE_OTHER)


def page_context(conn: sqlite3.Connection, admin: CurrentUser) -> dict[str, object]:
    """Template context of the roster page."""
    return {
        "active_tab": "users",
        "users": users_service.list_live_users(conn),
        "me_id": admin.id,
        "form_errors": {},
        "form_values": {},
        "toast": None,
    }


def password_toast(user: AuthUser, password: str, *, kind: str) -> dict[str, object]:
    """One-shot password toast payload."""
    return {"kind": kind, "email": user.email or user.name, "password": password}


def render_toast(
    request: Request, conn: sqlite3.Connection, admin: CurrentUser, toast: dict[str, object]
) -> HTMLResponse:
    """Toast in ``#user-feedback`` (HTMX) or the full page with it inline."""
    context = {**page_context(conn, admin), "toast": toast}
    hx = is_hx_request(request)
    template = TOAST_TEMPLATE if hx else LIST_TEMPLATE
    response = render_context(request, template, {**context, "oob_table": hx})
    response.headers["Cache-Control"] = "no-store"  # carries a one-shot password
    return response


def conflict(request: Request, exc: UserConflict) -> HTMLResponse:
    """409: error flash with ``HX-Reswap: none`` (HTMX) or the 409 page."""
    if not is_hx_request(request):
        return render(request, CONFLICT_TEMPLATE, HTTPStatus.CONFLICT, message=exc.message)
    response = render(
        request, FLASH_TEMPLATE, HTTPStatus.CONFLICT, level="error", message=exc.message
    )
    response.headers["HX-Reswap"] = "none"
    return response


def table_with_flash(
    request: Request, conn: sqlite3.Connection, admin: CurrentUser, message: str
) -> HTMLResponse:
    """Re-rendered roster table with a success flash."""
    return render(
        request,
        TABLE_TEMPLATE,
        users=users_service.list_live_users(conn),
        me_id=admin.id,
        flash_message=message,
    )


def edit_response(
    request: Request,
    user: AuthUser,
    *,
    me_id: int,
    errors: dict[str, str],
    values: dict[str, object] | None = None,
    status: int = HTTPStatus.OK,
) -> HTMLResponse:
    """Edit slide-over; on HTMX validation errors the form is retargeted and swapped."""
    form_values = values or {
        "email": user.email or "",
        "name": user.name,
        "is_admin": user.is_admin,
    }
    context: dict[str, object] = {
        "target": user,
        "me_id": me_id,
        "errors": errors,
        "form_values": form_values,
        "hx_enabled": is_hx_request(request),
    }
    if is_hx_request(request) and errors:
        response = render(request, EDIT_TEMPLATE, status, **context)
        response.headers["HX-Retarget"] = "#user-edit-form"
        response.headers["HX-Reswap"] = "outerHTML"
        return response
    return render(
        request,
        SLIDEOVER_TEMPLATE,
        status,
        slide_over_title=f"Edit {user.email or user.name}",
        form_include=EDIT_TEMPLATE,
        **context,
    )
