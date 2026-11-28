"""Settings router: the categories, currency and FX, and preferences pages (T-067, T-UR13).

One full page per ``?tab=`` value on the new shell (ADR-0107); an HTMX request for a page gets the
same page, whose regions select what they refresh. The category forms post to the ``/categories``
endpoints, so there is one copy of the business logic. ``GET /settings/close`` returns an empty
body. Tab contexts come from :mod:`budget_planner.services.settings_drawer` (T-Q267).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from types import MappingProxyType
from typing import get_args

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from budget_planner.services import settings_drawer
from budget_planner.web.deps import current_user_id, get_db
from budget_planner.web.params import query_choice
from budget_planner.web.paths import SETTINGS_PATH
from budget_planner.web.rendering import render_context
from budget_planner.web.settings_view import settings_page_context

_PAGES: Mapping[str, str] = MappingProxyType(
    {
        "categories": "pages/settings/categories.html",
        "fx": "pages/settings/currency-fx.html",
        "prefs": "pages/settings/preferences.html",
    }
)

router = APIRouter(prefix=SETTINGS_PATH, tags=["settings"])


@router.get("", response_class=HTMLResponse)
def drawer(
    request: Request,
    tab: str | None = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    """Return the Settings page with the requested tab active."""
    picked = query_choice("tab", tab, get_args(settings_drawer.TabKind))
    context = settings_page_context(settings_drawer.drawer_context(conn, user_id, picked))
    return render_context(request, _PAGES[settings_drawer.coerce_tab(picked)], context)


@router.get("/close", response_class=HTMLResponse)
def close() -> HTMLResponse:
    """Return an empty fragment so HTMX can swap away the drawer contents."""
    return HTMLResponse("")
