"""FastAPI dependencies for the web layer: DB connection, settings access,
and the current user id surface (T-D16 / ADR-0061 §5)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from fastapi import Request

from budget_planner.config import Settings, get_settings as _get_settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.request_ctx import RequestCtx


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
    """Build a :class:`RequestCtx` from the inbound request (T-D14).

    Pulls the client IP from ``request.client`` (falls back to ``None``
    for ASGI test transports that leave the field unset), the user-agent
    header verbatim, and — when T-D02 lands — the acting session user +
    opaque session id off ``request.state``. Routers depend on this to
    thread the context into services, which pass it through to
    :func:`write_audit`.

    The attribute probes use ``getattr`` with a ``None`` default so this
    dependency works in test environments and pre-T-D02 code paths where
    ``request.state`` has not been populated by an auth middleware.
    """
    ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    user = getattr(request.state, "user", None)
    session_id = getattr(request.state, "session_id", None)
    user_id: int | None = None
    if user is not None:
        user_id_attr = getattr(user, "id", None)
        if user_id_attr is not None:
            user_id = int(user_id_attr)
    return RequestCtx(
        ip=ip,
        user_id=user_id,
        session_id=session_id,
        user_agent=user_agent,
    )


def current_user_id(request: Request) -> int:
    """Return the current authenticated user id.

    Reads ``request.state.user.id`` which the auth middleware (T-D02) attaches
    after a successful session lookup. Until T-D02 lands we fall back to the
    legacy single-user id ``1`` so existing routes stay functional and tests
    do not need to stand up auth plumbing.

    TODO(T-D02): remove dev fallback — once the auth middleware is wired every
    unauthenticated request should be rejected before reaching this dep.
    """
    user = getattr(request.state, "user", None)
    if user is None:
        return 1
    return int(user.id)
