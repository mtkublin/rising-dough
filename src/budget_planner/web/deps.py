"""FastAPI dependencies for the web layer: DB connection, settings access,
and the current user id surface (T-D16 / ADR-0061 §5)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

from fastapi import Request

from budget_planner.config import Settings, get_settings as _get_settings
from budget_planner.db.connection import get_connection


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
