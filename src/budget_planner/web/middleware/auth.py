"""Session hydration + authentication gate (T-D02b, ADR-0033 §5, ADR-0070).

For every request except ``/static/*`` the middleware:

1. reads the session cookie (``__Host-session``, or ``session`` under
   ``env=dev`` — :func:`~budget_planner.web.auth_cookies.session_cookie_name`);
2. resolves it via :func:`budget_planner.services.auth.load_session_user`
   (which also slides the server-side expiry);
3. on success sets ``request.state.user`` to a frozen :class:`CurrentUser`
   and ``request.state.session_id`` to the raw cookie value, and re-issues
   the cookie so the browser ``Max-Age`` slides too;
4. on a protected path without a live session, answers with a login
   redirect (HTML), ``401`` + ``HX-Redirect`` (HTMX), or ``401`` JSON.

A stale cookie (unknown / revoked / expired) is deleted on the response.

Ordering (outermost first, ADR-0070 §6): RequestId → SecurityHeaders →
**AuthRequired** → CSRF → routers. T-D18's must-change-password redirect
and T-D17's admin guard slot between this layer and CSRF and read
``request.state.user``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from types import MappingProxyType
from typing import Final
from urllib.parse import quote, urlsplit

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from budget_planner.config import Settings
from budget_planner.logging import get_logger
from budget_planner.repositories.auth_users import AuthUser
from budget_planner.services import auth as auth_service
from budget_planner.services.connections import get_connection
from budget_planner.web.auth_cookies import (
    DEFAULT_LANDING,
    LOGIN_PATH,
    clear_session_cookie,
    safe_next,
    session_cookie_name,
    set_session_cookie,
)
from budget_planner.web.middleware.asgi import (
    RESPONSE_START,
    add_cookie,
    http_only,
    set_state,
    sets_cookie,
)

#: Paths reachable without a session (exact match).
EXEMPT_PATHS: Final = frozenset(
    {
        "/health",
        "/ready",
        "/healthz",
        "/health/replication",
        LOGIN_PATH,
        f"{LOGIN_PATH}/begin",
        f"{LOGIN_PATH}/finish",
    }
)
#: Path prefixes reachable without a session and never hydrated.
STATIC_PREFIX: Final = "/static/"

_UNAUTHORIZED_BODY: Final = MappingProxyType({"error": "unauthorized"})
_log = get_logger("budget_planner.auth")


@dataclass(frozen=True, slots=True, kw_only=True)
class CurrentUser:
    """The authenticated principal on ``request.state.user`` (no secrets)."""

    id: int
    email: str | None
    name: str
    is_admin: bool
    must_change_password: bool

    @classmethod
    def from_auth_user(cls, user: AuthUser) -> CurrentUser:
        return cls(
            id=user.id,
            email=user.email,
            name=user.name,
            is_admin=user.is_admin,
            must_change_password=user.must_change_password,
        )


def is_exempt(path: str) -> bool:
    """True when *path* is reachable without a session (ADR-0070 §4)."""
    return path in EXEMPT_PATHS or path.startswith(STATIC_PREFIX)


def _resolve(settings: Settings, session_id: str) -> tuple[CurrentUser, datetime] | None:
    conn = get_connection(settings)
    try:
        loaded = auth_service.load_session_user(conn, session_id)
    except sqlite3.Error as exc:
        # Fail closed: a DB error means "not authenticated", but say so loudly.
        _log.error("session_lookup_failed", error=str(exc))
        return None
    finally:
        conn.close()
    if loaded is None:
        return None
    return CurrentUser.from_auth_user(loaded[1]), loaded[0].expires_at


def _is_live(settings: Settings, session_id: str) -> bool:
    """True while *session_id* still resolves to a live session (no expiry slide)."""
    conn = get_connection(settings)
    try:
        return auth_service.load_session_user(conn, session_id, touch=False) is not None
    except sqlite3.Error as exc:
        _log.error("session_lookup_failed", error=str(exc))
        return False
    finally:
        conn.close()


def _login_url(next_path: str) -> str:
    target = safe_next(next_path)
    return f"{LOGIN_PATH}?next={quote(target, safe='')}"


def _hx_current_path(request: Request) -> str:
    current = request.headers.get("hx-current-url", "")
    parts = urlsplit(current)
    if not parts.path or (parts.netloc and parts.netloc != request.url.netloc):
        return DEFAULT_LANDING
    return f"{parts.path}?{parts.query}" if parts.query else parts.path


def _wants_json(request: Request) -> bool:
    accept = request.headers.get("accept", "").lower()
    return "application/json" in accept and "text/html" not in accept


def unauthenticated_response(request: Request) -> Response:
    """Build the ADR-0070 §4 response for an anonymous request."""
    if request.headers.get("hx-request", "").lower() == "true":
        return JSONResponse(
            dict(_UNAUTHORIZED_BODY),
            status_code=HTTPStatus.UNAUTHORIZED,
            headers={"HX-Redirect": _login_url(_hx_current_path(request))},
        )
    if _wants_json(request):
        return JSONResponse(dict(_UNAUTHORIZED_BODY), status_code=HTTPStatus.UNAUTHORIZED)
    path = request.url.path
    target = f"{path}?{request.url.query}" if request.url.query else path
    return RedirectResponse(_login_url(target), status_code=HTTPStatus.FOUND)


async def _refresh_cookie(
    message: Message, settings: Settings, session_id: str, expires_at: datetime | None
) -> None:
    """Slide or clear the session cookie on the response-start *message*.

    Sends nothing when the token was rotated or revoked while the request was in
    flight: the browser already holds the newer cookie (T-Q253, Q-062 H3-04).
    """
    if expires_at is None:
        add_cookie(message, lambda r: clear_session_cookie(r, settings))
    elif await run_in_threadpool(_is_live, settings, session_id):
        add_cookie(
            message,
            lambda r: set_session_cookie(r, settings, session_id, expires_at=expires_at),
        )


async def _authenticate(app: ASGIApp, scope: Scope, receive: Receive, send: Send) -> None:
    request = Request(scope, receive)
    path = request.url.path
    set_state(scope, user=None, session_id=None)
    if path.startswith(STATIC_PREFIX):
        await app(scope, receive, send)
        return

    settings: Settings = request.app.state.settings
    cookie_name = session_cookie_name(settings)
    session_id = request.cookies.get(cookie_name)
    resolved = await run_in_threadpool(_resolve, settings, session_id) if session_id else None
    user, expires_at = resolved if resolved is not None else (None, None)

    if user is not None:
        set_state(scope, user=user, session_id=session_id)
    elif not is_exempt(path):
        response = unauthenticated_response(request)
        if session_id:
            clear_session_cookie(response, settings)
        await response(scope, receive, send)
        return

    if not session_id:
        await app(scope, receive, send)
        return

    async def send_wrapper(message: Message) -> None:
        if message["type"] == RESPONSE_START and not sets_cookie(message, cookie_name):
            await _refresh_cookie(message, settings, session_id, expires_at)
        await send(message)

    await app(scope, receive, send_wrapper)


def auth_required_middleware(app: ASGIApp) -> ASGIApp:
    """Hydrate ``request.state.user`` and gate protected routes."""
    return http_only(app, _authenticate)


__all__ = [
    "EXEMPT_PATHS",
    "CurrentUser",
    "auth_required_middleware",
    "is_exempt",
    "unauthenticated_response",
]
