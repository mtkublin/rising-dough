"""Connection seam for the web layer (T-Q258, ADR-0130 §1).

``web`` must not import ``budget_planner.db`` (import-linter contract
"web does not import db"). Routers, dependencies and middleware obtain
connections through this module; the factory itself is unchanged.
"""

from __future__ import annotations

from budget_planner.db.connection import get_connection

__all__ = ["get_connection"]
