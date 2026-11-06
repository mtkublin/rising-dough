"""FastAPI dependencies for the web layer: DB connection, settings access,
and the current user id surface (T-D16 / ADR-0061 §5)."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from urllib.parse import quote, urlsplit

from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from budget_planner.config import Settings, get_settings as _get_settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories import sessions as sessions_repo
from budget_planner.repositories.sessions import session_handle
from budget_planner.web.auth_cookies import safe_next
from budget_planner.web.middleware.auth import CurrentUser

REAUTH_PATH = "/auth/reauth"
REAUTH_REQUIRED = "reauth_required"
_FALLBACK_NEXT = "/settings/security"


def get_settings_dep(request: Request) -> Settings:
    """Return the Settings object, preferring app.state override for tests."""
    override = getattr(request.app.state, "settings", None)
    if isinstance(override, Settings):
        return override
    return _get_settings()


def get_db(request: Request) -> Iterator[sqlite3.Connection]:
    """Yield a per-request SQLite connection with FK pragmas on."""
    settings = get_settings_dep(request)
    conn = get_connection(settings)
    try:
        yield conn
    finally:
        conn.close()


def get_request_ctx(request: Request) -> RequestCtx:
    """Build a :class:`RequestCtx` from the inbound request (T-D14, T-D02b).

    Pulls the client IP from ``request.client`` (``None`` for ASGI test
    transports that leave it unset), the user-agent header verbatim, and the
    acting session user + session id that ``AuthRequiredMiddleware`` put on
    ``request.state``. ``RequestCtx.session_id`` carries the non-secret
    :func:`session_handle`, never the raw cookie value (ADR-0067 §4).
    The ``getattr`` probes keep this usable on exempt routes (``/auth/login``)
    where no user is attached yet.
    """
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    user = getattr(request.state, "user", None)
    raw_session_id = getattr(request.state, "session_id", None)
    user_id = None if user is None else int(user.id)
    return RequestCtx(
        ip=ip,
        user_id=user_id,
        session_id=session_handle(raw_session_id) if raw_session_id else None,
        user_agent=user_agent,
    )


def current_user(request: Request) -> CurrentUser:
    """Return the authenticated :class:`CurrentUser`; 401 when absent.

    ``AuthRequiredMiddleware`` (T-D02b) rejects anonymous requests to
    protected routes before they reach a router, so this only fires if a
    route is wired up without the middleware (defence in depth).
    """
    user = getattr(request.state, "user", None)
    if not isinstance(user, CurrentUser):
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail="unauthorized")
    return user


def current_user_id(request: Request) -> int:
    """Return the authenticated user's id (``request.state.user.id``); 401 when absent."""
    return current_user(request).id


class ReauthRequired(Exception):  # noqa: N818  # control-flow signal, handled in web.errors
    """Raised by :func:`require_recent_auth`; carries the ready-made stale response."""

    def __init__(self, response: Response) -> None:
        super().__init__(REAUTH_REQUIRED)
        self.response = response


def reauth_now(request: Request) -> datetime:
    """Current time for re-auth checks; tests inject ``app.state.reauth_clock``."""
    clock: Callable[[], datetime] | None = getattr(request.app.state, "reauth_clock", None)
    return clock() if clock is not None else datetime.now(UTC)


def _same_origin_path(url: str, request: Request) -> str | None:
    parts = urlsplit(url)
    if not parts.path or (parts.netloc and parts.netloc != request.url.netloc):
        return None
    return f"{parts.path}?{parts.query}" if parts.query else parts.path


def _return_path(request: Request) -> str:
    """Page the user was on: HX-Current-URL, else Referer, else the Security tab.

    Never the POST route itself — a GET to it would 405.
    """
    for header in ("hx-current-url", "referer"):
        path = _same_origin_path(request.headers.get(header, ""), request)
        if path:
            return safe_next(path)
    return _FALLBACK_NEXT


def reauth_url(request: Request) -> str:
    """``/auth/reauth?next=<validated return path>``."""
    return f"{REAUTH_PATH}?next={quote(_return_path(request), safe='')}"


def reauth_required_response(request: Request) -> Response:
    """Stale-session response in the shape the caller can handle (ADR-0076 §2)."""
    url = reauth_url(request)
    if request.headers.get("hx-request", "").lower() == "true":
        return JSONResponse(
            {"error": REAUTH_REQUIRED},
            status_code=HTTPStatus.FORBIDDEN,
            headers={"HX-Redirect": url},
        )
    accept = request.headers.get("accept", "").lower()
    if "application/json" in accept and "text/html" not in accept:
        return JSONResponse(
            {"error": REAUTH_REQUIRED, "redirect": url}, status_code=HTTPStatus.FORBIDDEN
        )
    return RedirectResponse(url, status_code=HTTPStatus.SEE_OTHER)


def is_recently_authenticated(request: Request, conn: sqlite3.Connection) -> bool:
    """True when the session's last credential proof is within the re-auth window."""
    token = getattr(request.state, "session_id", None)
    session = sessions_repo.get_session(conn, token, now=reauth_now(request)) if token else None
    if session is None:
        return False
    window = timedelta(minutes=get_settings_dep(request).session_reauth_window_minutes)
    return reauth_now(request) - session.authenticated_at <= window


def require_recent_auth(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),  # noqa: B008
    _user: CurrentUser = Depends(current_user),  # noqa: B008
) -> None:
    """Route dependency: 403 / redirect to ``/auth/reauth`` when the login is stale."""
    if not is_recently_authenticated(request, conn):
        raise ReauthRequired(reauth_required_response(request))
