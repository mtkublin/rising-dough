"""Template context for Settings -> Security (T-Q267; ADR-0075).

Shared by the GET page and the password-form re-renders. Data comes from
:mod:`budget_planner.services.security_settings`; this module only adds the request-bound pieces.
"""

from __future__ import annotations

import sqlite3
from typing import Final

from fastapi import Request

from budget_planner.services import password_change as password_service
from budget_planner.services.auth import LABEL_MAX_LENGTH
from budget_planner.services.security_settings import security_view
from budget_planner.web.middleware.auth import CurrentUser

SECURITY_PATH: Final = "/settings/security"
PASSWORD_ANCHOR: Final = f"{SECURITY_PATH}#password"
PAGE_TEMPLATE: Final = "settings/security.html"


def security_context(
    request: Request, conn: sqlite3.Connection, user: CurrentUser
) -> dict[str, object]:
    """Template context shared by the GET page and password-form re-renders."""
    view = security_view(
        conn,
        user.id,
        session_token=getattr(request.state, "session_id", None),
        absolute_lifetime_days=request.app.state.settings.session_absolute_lifetime_days,
    )
    return {
        "active_tab": "security",
        "current_user": user,
        "session_rows": view.session_rows,
        "passkeys": view.passkeys,
        "label_max_length": LABEL_MAX_LENGTH,
        "min_length": password_service.MIN_PASSWORD_LENGTH,
        "forced": False,
        "next_path": SECURITY_PATH,
        "outcome": None,
        "throttle_error": None,
    }
