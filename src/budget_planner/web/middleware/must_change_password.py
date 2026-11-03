"""Forced password rotation gate (T-D18, ADR-0061 §4, ADR-0074 §3).

Runs directly inside :class:`~budget_planner.web.middleware.auth.AuthRequiredMiddleware`
(ADR-0070 §6), which has already put the session user on
``request.state.user``. While that user's ``must_change_password`` flag is
set, every path except :data:`EXEMPT_PATHS` / ``/static/*`` is answered with:

- HTML: ``302`` to ``/settings/password?next=<original>``;
- HTMX: ``403`` JSON + ``HX-Redirect`` to the same URL;
- JSON: ``403`` ``{"error": "password_change_required", "location": ...}``.

Anonymous requests pass through untouched.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Final
from urllib.parse import quote, urlsplit

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from budget_planner.web.auth_cookies import safe_next

PASSWORD_PATH: Final = "/settings/password"  # noqa: S105 — a URL path, not a secret
LOGOUT_PATH: Final = "/auth/logout"
STATIC_PREFIX: Final = "/static/"

#: Paths reachable while ``must_change_password`` is set (exact match).
EXEMPT_PATHS: Final = frozenset({PASSWORD_PATH, LOGOUT_PATH, "/health", "/ready", "/healthz"})

ERROR_CODE: Final = "password_change_required"
_BODY: Final = {"error": ERROR_CODE, "location": PASSWORD_PATH}


def is_exempt(path: str) -> bool:
    """True when *path* stays reachable during a forced rotation."""
    return path in EXEMPT_PATHS or path.startswith(STATIC_PREFIX)


def password_url(next_path: str) -> str:
    """Return the rotation URL carrying a safe ``next`` (``/`` is dropped)."""
    target = safe_next(next_path)
    if target == "/" or urlsplit(target).path == PASSWORD_PATH:
        return PASSWORD_PATH
    return f"{PASSWORD_PATH}?next={quote(target, safe='')}"


def _request_target(request: Request) -> str:
    path = request.url.path
    return f"{path}?{request.url.query}" if request.url.query else path


def _hx_target(request: Request) -> str:
    parts = urlsplit(request.headers.get("hx-current-url", ""))
    if not parts.path or (parts.netloc and parts.netloc != request.url.netloc):
        return "/"
    return f"{parts.path}?{parts.query}" if parts.query else parts.path


def _wants_json(request: Request) -> bool:
    accept = request.headers.get("accept", "").lower()
    return "application/json" in accept and "text/html" not in accept


def rotation_required_response(request: Request) -> Response:
    """Build the ADR-0074 §3 response for a gated request."""
    if request.headers.get("hx-request", "").lower() == "true":
        return JSONResponse(
            _BODY,
            status_code=HTTPStatus.FORBIDDEN,
            headers={"HX-Redirect": password_url(_hx_target(request))},
        )
    if _wants_json(request):
        return JSONResponse(_BODY, status_code=HTTPStatus.FORBIDDEN)
    return RedirectResponse(password_url(_request_target(request)), status_code=HTTPStatus.FOUND)


class MustChangePasswordMiddleware(BaseHTTPMiddleware):
    """Send a user flagged ``must_change_password`` to ``/settings/password``."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        user = getattr(request.state, "user", None)
        if user is not None and user.must_change_password and not is_exempt(request.url.path):
            return rotation_required_response(request)
        return await call_next(request)


__all__ = [
    "EXEMPT_PATHS",
    "PASSWORD_PATH",
    "MustChangePasswordMiddleware",
    "is_exempt",
    "password_url",
    "rotation_required_response",
]
