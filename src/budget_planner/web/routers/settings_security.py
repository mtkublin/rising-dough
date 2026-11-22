"""``/settings/security`` — the Security tab in Settings (T-D47, ADR-0075).

One page holding Password, Passkeys and Sessions. Thin layer: the password
form posts to :mod:`budget_planner.web.routers.settings_password`, passkey
ceremonies use ``/auth/register/begin|finish`` and revoke buttons post to
``/auth/sessions/<handle>/revoke`` / ``/auth/passkeys/<id>/revoke``. Not
exempt from ``MustChangePasswordMiddleware`` — forced users never reach it.
The page context lives in :mod:`budget_planner.web.security_context` (T-Q267).
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from budget_planner.web.deps import current_user, get_db
from budget_planner.web.middleware.auth import CurrentUser
from budget_planner.web.rendering import render_context
from budget_planner.web.security_context import PAGE_TEMPLATE, security_context

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/security", response_class=HTMLResponse)
def security_page(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user: CurrentUser = Depends(current_user),
) -> HTMLResponse:
    """Render Password, Passkeys and Sessions for the signed-in user."""
    return render_context(request, PAGE_TEMPLATE, security_context(request, conn, user))
