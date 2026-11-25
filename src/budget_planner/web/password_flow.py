"""Response helpers for the self-service password change (T-Q267; T-D18, ADR-0074).

Target resolution and the form/page renderer, moved out of ``web/routers/settings_password.py``.
"""

from __future__ import annotations

import sqlite3
from http import HTTPStatus
from types import MappingProxyType
from typing import Final

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from budget_planner.config import Settings
from budget_planner.services import password_change as password_service, rate_limit
from budget_planner.web.auth_cookies import DEFAULT_LANDING, safe_next, set_session_cookie
from budget_planner.web.auth_deps import rate_limit_now
from budget_planner.web.http_headers import HX_REDIRECT
from budget_planner.web.middleware.auth import CurrentUser
from budget_planner.web.middleware.must_change_password import PASSWORD_PATH
from budget_planner.web.rendering import is_hx_request, render
from budget_planner.web.security_context import SECURITY_PATH, security_context

PAGE: Final = "pages/auth/force-password.html"
FORM: Final = "fragments/forms/password-form.html"
SECURITY_PAGE: Final = "pages/settings/security.html"
#: Field -> (input id, label the form prints): the summary links to the field it names.
INPUTS: Final = MappingProxyType(
    {
        "current_password": ("current-password", "current password"),
        "new_password": ("new-password", "new password"),
        "confirm_password": ("confirm-password", "confirm new password"),
    }
)
THROTTLED_FORM_ERROR: Final = "Too many attempts. Please wait a few minutes and try again."


def landing_target(next_path: str | None) -> str:
    """Sanitised ``next`` path, never the password page itself."""
    target = safe_next(next_path)
    return DEFAULT_LANDING if target.split("?", 1)[0] == PASSWORD_PATH else target


def default_target(user: CurrentUser, next_path: str | None) -> str:
    """Forced users go on to ``next``; others stay in Settings -> Security."""
    target = landing_target(next_path)
    if user.must_change_password:
        return target
    return SECURITY_PATH if target == DEFAULT_LANDING else target


def attempts_text(
    request: Request, conn: sqlite3.Connection, settings: Settings, user: CurrentUser
) -> str:
    """``"2 attempts left."`` for the current-password error (services.rate_limit.attempts_left)."""
    left = rate_limit.attempts_left(
        conn,
        rate_limit.SCOPE_PASSWORD_CHANGE,
        rate_limit.user_identity(user.id),
        rate_limit.password_change_rules(settings),
        now=rate_limit_now(request),
    )
    if left is None:
        return ""
    return f"{left} attempt{'' if left == 1 else 's'} left."


def summary_rows(
    outcome: password_service.PasswordChangeOutcome | None,
) -> tuple[tuple[str, str, str], ...]:
    """(input id, label, message) per invalid field for the 422 summary."""
    if outcome is None:
        return ()
    return tuple((INPUTS[e.field][0], INPUTS[e.field][1], e.message) for e in outcome.errors)


def render_form(
    request: Request,
    conn: sqlite3.Connection,
    user: CurrentUser,
    *,
    next_path: str,
    outcome: password_service.PasswordChangeOutcome | None = None,
    throttled: bool = False,
    attempts: str | None = None,
) -> HTMLResponse:
    """The password form: page, Security tab or HTMX fragment (422 on failure, 429 throttled)."""
    failed = outcome is not None and not outcome.ok
    status = HTTPStatus.UNPROCESSABLE_ENTITY if failed else HTTPStatus.OK
    context = {
        "current_user": user,
        "forced": user.must_change_password,
        "next_path": next_path,
        "outcome": outcome,
        "errors": {e.field: e.message for e in outcome.errors} if outcome else {},
        "summary_rows": summary_rows(outcome),
        "attempts_text": attempts,
        "min_length": password_service.MIN_PASSWORD_LENGTH,
        "throttle_error": THROTTLED_FORM_ERROR if throttled else None,
    }
    if not user.must_change_password and not is_hx_request(request):
        context = {**security_context(request, conn, user), **context}
        page = SECURITY_PAGE
    else:
        page = FORM if is_hx_request(request) else PAGE
    return render(
        request,
        page,
        status_code=HTTPStatus.TOO_MANY_REQUESTS if throttled else status,
        **context,
    )


def success_response(
    request: Request,
    settings: Settings,
    outcome: password_service.PasswordChangeOutcome,
    target: str,
) -> Response:
    """HX-Redirect (HTMX) or 303 to ``target``, carrying the rotated session cookie if any."""
    done: Response
    if is_hx_request(request):
        done = Response(status_code=HTTPStatus.NO_CONTENT, headers={HX_REDIRECT: target})
    else:
        done = RedirectResponse(target, status_code=HTTPStatus.SEE_OTHER)
    if outcome.rotated is not None:
        set_session_cookie(
            done,
            settings,
            outcome.rotated.token,
            expires_at=outcome.rotated.session.expires_at,
        )
    return done
