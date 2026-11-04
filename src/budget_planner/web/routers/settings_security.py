"""``/settings/security`` — the Security tab in Settings (T-D47, ADR-0075).

One page holding Password, Passkeys and Sessions. Thin layer: the password
form posts to :mod:`budget_planner.web.routers.settings_password`, passkey
ceremonies use ``/auth/register/begin|finish`` and revoke buttons post to
``/auth/sessions/<handle>/revoke`` / ``/auth/passkeys/<id>/revoke``. Not
exempt from ``MustChangePasswordMiddleware`` — forced users never reach it.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Final

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from budget_planner.repositories import sessions as sessions_repo, webauthn as webauthn_repo
from budget_planner.services import password_change as password_service
from budget_planner.web.deps import current_user, get_db
from budget_planner.web.middleware.auth import CurrentUser
from budget_planner.web.rendering import render
from budget_planner.web.routers.auth import LABEL_MAX_LENGTH

SECURITY_PATH: Final = "/settings/security"
PASSWORD_ANCHOR: Final = f"{SECURITY_PATH}#password"
PAGE_TEMPLATE: Final = "settings/security.html"

router = APIRouter(prefix="/settings", tags=["settings"])


def security_context(
    request: Request, conn: sqlite3.Connection, user: CurrentUser
) -> dict[str, Any]:
    """Template context shared by the GET page and password-form re-renders."""
    current_id = getattr(request.state, "session_id", None)
    sessions = sessions_repo.list_active_sessions(conn, user.id)
    return {
        "active_tab": "security",
        "current_user": user,
        "session_rows": [{"session": s, "is_current": s.id == current_id} for s in sessions],
        "passkeys": webauthn_repo.list_credentials(conn, user.id),
        "label_max_length": LABEL_MAX_LENGTH,
        "min_length": password_service.MIN_PASSWORD_LENGTH,
        "forced": False,
        "next_path": SECURITY_PATH,
        "outcome": None,
        "throttle_error": None,
    }


@router.get("/security", response_class=HTMLResponse)
def security_page(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user: CurrentUser = Depends(current_user),
) -> HTMLResponse:
    """Render Password, Passkeys and Sessions for the signed-in user."""
    return render(request, PAGE_TEMPLATE, **security_context(request, conn, user))
