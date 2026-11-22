"""Forced password rotation gate (T-D18, ADR-0061 §4, ADR-0074 §3).

Runs directly inside :func:`~budget_planner.web.middleware.auth.auth_required_middleware`
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
from types import MappingProxyType
from typing import Final
from urllib.parse import quote, urlsplit

from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Receive, Scope, Send

from budget_planner.web.auth_cookies import DEFAULT_LANDING, safe_next
from budget_planner.web.http_headers import (
    HTML_MEDIA_TYPE,
    HX_CURRENT_URL,
    HX_REDIRECT,
    HX_REQUEST,
    JSON_MEDIA_TYPE,
)
from budget_planner.web.middleware.asgi import http_only

PASSWORD_PATH: Final = "/settings/password"  # noqa: S105 — a URL path, not a secret
LOGOUT_PATH: Final = "/auth/logout"
STATIC_PREFIX: Final = "/static/"

#: Paths reachable while ``must_change_password`` is set (exact match).
EXEMPT_PATHS: Final = frozenset(
    {PASSWORD_PATH, LOGOUT_PATH, "/health", "/health/replication", "/ready", "/healthz"}
)

ERROR_CODE: Final = "password_change_required"
_BODY: Final = MappingProxyType({"error": ERROR_CODE, "location": PASSWORD_PATH})


def is_exempt(path: str) -> bool:
    """True when *path* stays reachable during a forced rotation."""
    return path in EXEMPT_PATHS or path.startswith(STATIC_PREFIX)


def password_url(next_path: str) -> str:
    """Return the rotation URL carrying a safe ``next`` (``/`` is dropped)."""
    target = safe_next(next_path)
    if target == DEFAULT_LANDING or urlsplit(target).path == PASSWORD_PATH:
        return PASSWORD_PATH
    return f"{PASSWORD_PATH}?next={quote(target, safe='')}"


def _request_target(request: Request) -> str:
    path = request.url.path
    return f"{path}?{request.url.query}" if request.url.query else path


def _hx_target(request: Request) -> str:
    parts = urlsplit(request.headers.get(HX_CURRENT_URL, ""))
    if not parts.path or (parts.netloc and parts.netloc != request.url.netloc):
        return DEFAULT_LANDING
    return f"{parts.path}?{parts.query}" if parts.query else parts.path


def _wants_json(request: Request) -> bool:
    accept = request.headers.get("accept", "").lower()
    return JSON_MEDIA_TYPE in accept and HTML_MEDIA_TYPE not in accept


def rotation_required_response(request: Request) -> Response:
    """Build the ADR-0074 §3 response for a gated request."""
    if request.headers.get(HX_REQUEST, "").lower() == "true":
        return JSONResponse(
            dict(_BODY),
            status_code=HTTPStatus.FORBIDDEN,
            headers={HX_REDIRECT: password_url(_hx_target(request))},
        )
    if _wants_json(request):
        return JSONResponse(dict(_BODY), status_code=HTTPStatus.FORBIDDEN)
    return RedirectResponse(password_url(_request_target(request)), status_code=HTTPStatus.FOUND)


async def _rotation_gate(app: ASGIApp, scope: Scope, receive: Receive, send: Send) -> None:
    request = Request(scope, receive)
    user = getattr(request.state, "user", None)
    if user is not None and user.must_change_password and not is_exempt(request.url.path):
        await rotation_required_response(request)(scope, receive, send)
        return
    await app(scope, receive, send)


def must_change_password_middleware(app: ASGIApp) -> ASGIApp:
    """Send a user flagged ``must_change_password`` to ``/settings/password``."""
    return http_only(app, _rotation_gate)


__all__ = [
    "EXEMPT_PATHS",
    "PASSWORD_PATH",
    "is_exempt",
    "must_change_password_middleware",
    "password_url",
    "rotation_required_response",
]
