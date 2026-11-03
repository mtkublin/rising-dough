"""FastAPI dependencies for the web layer: DB connection, settings access,
and the current user id surface (T-D16 / ADR-0061 §5)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from http import HTTPStatus

from fastapi import HTTPException, Request

from budget_planner.config import Settings, get_settings as _get_settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories.sessions import session_handle
from budget_planner.web.middleware.auth import CurrentUser


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
