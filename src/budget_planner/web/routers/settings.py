"""Settings drawer router (T-067).

Serves the Settings page / right-side fragment with three internal tabs:

- Categories — lifts the existing `/categories` CRUD into the drawer. Form
  posts still target the `/categories` endpoints, so there is only one copy
  of the business logic (ADR-0021 functional-first, thin web).
- FX — read-only list of cached FX rates. Editing is a v2 concern.
- Preferences — read-only base currency + display timezone (ADR-0006 / ADR-0007).

The drawer deliberately does **not** change the browser URL. HTMX swaps the
fragment HTML into `#drawer-root`; `GET /settings/close` returns an empty body
so clients can clear the drawer via the same mechanism. Tab contexts come from
:mod:`budget_planner.services.settings_drawer` (T-Q267).
"""

from __future__ import annotations

import sqlite3
from typing import get_args

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from budget_planner.services import settings_drawer
from budget_planner.web.deps import current_user_id, get_db
from budget_planner.web.params import query_choice
from budget_planner.web.paths import SETTINGS_PATH
from budget_planner.web.rendering import is_hx_request, render_context

router = APIRouter(prefix=SETTINGS_PATH, tags=["settings"])


@router.get("", response_class=HTMLResponse)
def drawer(
    request: Request,
    tab: str | None = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    """Return the Settings page (or HTMX drawer fragment) with the requested tab active."""
    picked = query_choice("tab", tab, get_args(settings_drawer.TabKind))
    context = settings_drawer.drawer_context(conn, user_id, picked)
    # Rising Dough v2 — Settings is a full page (ADR-0051 §7). The template
    # extends base.html and reuses the existing panel fragments.
    template = "settings/_drawer.html" if is_hx_request(request) else "settings/index.html"
    return render_context(request, template, context)


@router.get("/close", response_class=HTMLResponse)
def close() -> HTMLResponse:
    """Return an empty fragment so HTMX can swap away the drawer contents."""
    return HTMLResponse("")
