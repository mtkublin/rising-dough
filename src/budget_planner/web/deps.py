"""FastAPI dependencies for the web layer: DB connection + settings access."""

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
