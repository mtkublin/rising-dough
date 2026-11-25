"""Response helpers for the admin user roster (T-Q267, T-UR14; ADR-0061, ADR-0073, ADR-0152).

Renderers for the roster page, the one-time password dialog, the edit, reset and delete dialogs and
the 404/409 flashes, moved out of ``web/routers/settings_users.py``. Dialogs go through
``web.dialogs`` (they land in ``#modal-root``).
"""

from __future__ import annotations

import sqlite3
from http import HTTPStatus
from typing import Final

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

from budget_planner.services import users as users_service
from budget_planner.services.users import AuthUser, UserConflict
from budget_planner.web.dialogs import MODAL_ROOT, dialog_response
from budget_planner.web.htmx import Event, trigger
from budget_planner.web.http_headers import HX_RESWAP, HX_RETARGET
from budget_planner.web.middleware.auth import CurrentUser
from budget_planner.web.rendering import is_hx_request, render, render_context
from budget_planner.web.settings_view import (
    UserDialogView,
    live_admin_count,
    user_dialog_view,
    user_row_view,
    user_rows,
)

LIST_PATH: Final = "/settings/users"
LIST_TEMPLATE: Final = "pages/settings/users.html"
TABLE_TEMPLATE: Final = "fragments/tables/users-table.html"
ROW_TEMPLATE: Final = "fragments/rows/user-row.html"
ONE_TIME_DIALOG: Final = "fragments/dialogs/one-time-password.html"
EDIT_DIALOG: Final = "fragments/dialogs/edit-user.html"
DELETE_DIALOG: Final = "fragments/dialogs/delete-user.html"
RESET_DIALOG: Final = "fragments/dialogs/reset-password.html"
SUMMARY_TEMPLATE: Final = "fragments/forms/error-summary.html"
FLASH_TEMPLATE: Final = "partials/_flash.html"
NOT_FOUND_TEMPLATE: Final = "pages/errors/404.html"
CONFLICT_TEMPLATE: Final = "pages/errors/409.html"
RESET_NOTE: Final = "Their existing sessions have been signed out."
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


def page_context(
    request: Request, conn: sqlite3.Connection, admin: CurrentUser
) -> dict[str, object]:
    """Template context of the roster page."""
    tz = request.app.state.settings.display_timezone
    return {
        "active_tab": "users",
        "rows": user_rows(users_service.list_live_users(conn), me_id=admin.id, tz=tz),
        "toast": None,
        "form_summary": (),
    }


def password_toast(user: AuthUser, password: str, *, kind: str) -> dict[str, object]:
    """One-shot password payload for the one-time password dialog."""
    return {
        "kind": kind,
        "email": user.email or user.name,
        "name": user.name,
        "password": password,
        "note": RESET_NOTE if kind == "reset" else "",
    }


def render_toast(
    request: Request, conn: sqlite3.Connection, admin: CurrentUser, toast: dict[str, object]
) -> HTMLResponse:
    """One-time password dialog plus the refreshed table (HTMX) or the page with it inline."""
    context = {**page_context(request, conn, admin), "toast": toast}
    if not is_hx_request(request):
        response = render_context(request, LIST_TEMPLATE, context)
    else:
        dialog = dialog_response(request, ONE_TIME_DIALOG, context)
        table = render_context(request, TABLE_TEMPLATE, {**context, "oob_table": True})
        response = HTMLResponse(bytes(dialog.body).decode() + bytes(table.body).decode())
        response.headers[HX_RETARGET] = MODAL_ROOT
        response.headers[HX_RESWAP] = "innerHTML"
    response.headers["Cache-Control"] = "no-store"  # carries a one-shot password
    return response


def conflict(request: Request, exc: UserConflict) -> HTMLResponse:
    """409: error flash with ``HX-Reswap: none`` (HTMX) or the 409 page."""
    if not is_hx_request(request):
        return render(request, CONFLICT_TEMPLATE, HTTPStatus.CONFLICT, message=exc.message)
    response = render(
        request, FLASH_TEMPLATE, HTTPStatus.CONFLICT, level="error", message=exc.message
    )
    response.headers[HX_RESWAP] = "none"
    trigger(response, Event.DIALOG_CLOSE)  # an open dialog would hide the flash behind it
    return response


def dialog_view(
    conn: sqlite3.Connection,
    admin: CurrentUser,
    target: AuthUser,
    *,
    name: str | None = None,
    is_admin: bool | None = None,
) -> UserDialogView:
    """Values of the edit, reset and delete dialogs for ``target`` (live admin count included)."""
    live_admins = live_admin_count(users_service.list_live_users(conn))
    return user_dialog_view(
        target, me_id=admin.id, live_admins=live_admins, name=name, is_admin=is_admin
    )


def user_dialog(
    request: Request,
    conn: sqlite3.Connection,
    admin: CurrentUser,
    template: str,
    target: AuthUser,
) -> HTMLResponse:
    """Open the edit, reset or delete dialog for ``target`` in ``#modal-root``."""
    return dialog_response(
        request, template, {"view": dialog_view(conn, admin, target), "errors": {}}
    )


def row_context(
    request: Request, conn: sqlite3.Connection, admin: CurrentUser, user_id: int
) -> dict[str, object]:
    """Context of one roster row (``fragments/rows/user-row``) after a save."""
    listed = next(u for u in users_service.list_live_users(conn) if u.id == user_id)
    tz = request.app.state.settings.display_timezone
    return {"row": user_row_view(listed, me_id=admin.id, tz=tz)}
