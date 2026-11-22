"""Connection seam for the web layer (T-Q258, ADR-0130 §1).

``web`` must not import ``budget_planner.db`` (import-linter contract
"web does not import db"). Routers, dependencies and middleware obtain
connections through this module; the factory itself is unchanged.
"""

from __future__ import annotations

import sqlite3

from budget_planner.db.connection import get_connection
from budget_planner.repositories import users as users_repo


def ping(conn: sqlite3.Connection) -> None:
    """Trivial schema read for the readiness probe (T-Q235); raises if the DB cannot answer."""
    users_repo.has_live_admin(conn)


__all__ = ["get_connection", "ping"]
