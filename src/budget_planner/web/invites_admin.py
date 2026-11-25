"""Response helpers for the invite part of the Users page (T-UR20a; ADR-0134 section 1, ADR-0148).

The create dialog, the one-time invite link dialog (plus the refreshed table out of band), the
revoke confirm and the 404 / 409 flashes, so ``web/routers/settings_invites.py`` only holds
handlers. The link response carries the plain token, so it is ``no-store``.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from http import HTTPStatus
from typing import Final

from fastapi import Request
from fastapi.responses import HTMLResponse

from budget_planner.services import invites as invites_service
from budget_planner.services.invites import IssuedInvite
from budget_planner.web.dialogs import MODAL_ROOT, dialog_response
from budget_planner.web.http_headers import HX_RESWAP, HX_RETARGET
from budget_planner.web.middleware.asgi import CACHE_CONTROL_HEADER, NO_STORE
from budget_planner.web.middleware.auth import CurrentUser
from budget_planner.web.rendering import is_hx_request, render, render_context
from budget_planner.web.settings_view import invite_row_view
from budget_planner.web.users_admin import (
    FLASH_TEMPLATE,
    LIST_TEMPLATE,
    NOT_FOUND_TEMPLATE,
    TABLE_TEMPLATE,
    page_context,
)

CREATE_DIALOG: Final = "fragments/dialogs/create-invite.html"
LINK_DIALOG: Final = "fragments/dialogs/invite-link.html"
REVOKE_DIALOG: Final = "fragments/dialogs/revoke-invite.html"
NOT_FOUND_MESSAGE: Final = "Invite not found"


def create_context(*, email: str = "", is_admin: bool = False) -> dict[str, object]:
    """Values of the create invite dialog (submitted values come back on a 422)."""
    return {"email": email, "is_admin": is_admin, "errors": {}}


def link_response(
    request: Request,
    conn: sqlite3.Connection,
    admin: CurrentUser,
    issued: IssuedInvite,
    *,
    now: datetime,
    resent: bool,
) -> HTMLResponse:
    """The invite link dialog plus the refreshed table (HTMX), or the page with the link inline."""
    tz = request.app.state.settings.display_timezone
    row = invite_row_view(issued.invite, now=now, tz=tz)
    link = invites_service.invite_link(request.app.state.settings.webauthn_origin, issued.token)
    context = {
        **page_context(request, conn, admin, now=now),
        "invite_link": link,
        "invite": row,
        "resent": resent,
    }
    if not is_hx_request(request):
        response = render_context(request, LIST_TEMPLATE, context)
    else:
        dialog = dialog_response(request, LINK_DIALOG, context)
        table = render_context(request, TABLE_TEMPLATE, {**context, "oob_table": True})
        response = HTMLResponse(bytes(dialog.body).decode() + bytes(table.body).decode())
        response.headers[HX_RETARGET] = MODAL_ROOT
        response.headers[HX_RESWAP] = "innerHTML"
    response.headers[CACHE_CONTROL_HEADER] = NO_STORE  # carries the plain invite token
    return response


def invite_not_found(request: Request) -> HTMLResponse:
    """404 for a missing invite: an error flash (HTMX) or the app's 404 page."""
    if is_hx_request(request):
        return render(
            request,
            FLASH_TEMPLATE,
            HTTPStatus.NOT_FOUND,
            level="error",
            message=NOT_FOUND_MESSAGE,
        )
    return render(request, NOT_FOUND_TEMPLATE, HTTPStatus.NOT_FOUND, entity="invite", entity_id=0)
