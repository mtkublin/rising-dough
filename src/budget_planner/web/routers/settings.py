"""Settings drawer router (T-067).

Serves the right-side slide-over Settings fragment with three internal tabs:

- Categories — lifts the existing `/categories` CRUD into the drawer. Form
  posts still target the `/categories` endpoints, so there is only one copy
  of the business logic (ADR-0021 functional-first, thin web).
- FX — read-only list of cached FX rates. Editing is a v2 concern.
- Preferences — read-only base currency + display timezone (ADR-0006 / ADR-0007).

The drawer deliberately does **not** change the browser URL. HTMX swaps the
fragment HTML into `#drawer-root`; `GET /settings/close` returns an empty body
so clients can clear the drawer via the same mechanism.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Final, Literal, get_args

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse

from budget_planner.domain.enums import Direction
from budget_planner.repositories import (
    categories as categories_repo,
    fx as fx_repo,
)
from budget_planner.services import preferences as preferences_svc
from budget_planner.web.deps import current_user_id, get_db
from budget_planner.web.rendering import render

TabKind = Literal["categories", "fx", "prefs"]
_VALID_TABS: Final[tuple[TabKind, ...]] = get_args(TabKind)
_DEFAULT_TAB: Final[TabKind] = "categories"
_FX_LIMIT: Final[int] = 50

router = APIRouter(prefix="/settings", tags=["settings"])


def _coerce_tab(raw: str | None) -> TabKind:
    """Return a valid tab identifier, defaulting to Categories on absent/invalid."""
    if raw is None:
        return _DEFAULT_TAB
    for valid in _VALID_TABS:
        if raw == valid:
            return valid
    return _DEFAULT_TAB


@router.get("", response_class=HTMLResponse)
def drawer(
    request: Request,
    tab: str | None = Query(default=None),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    """Return the Settings drawer fragment with the requested tab active."""
    active_tab = _coerce_tab(tab)
    context: dict[str, Any] = {"active_tab": active_tab}
    if active_tab == "categories":
        all_cats = categories_repo.list_all(conn, user_id)
        context["categories"] = all_cats
        # ADR-0056 §8 — grouped sections (Expense · Income · System).
        context["expense_categories"] = [
            c for c in all_cats if (not c.is_system) and c.direction is Direction.EXPENSE
        ]
        context["income_categories"] = [
            c for c in all_cats if (not c.is_system) and c.direction is Direction.INCOME
        ]
        context["system_categories"] = [c for c in all_cats if c.is_system]
        # Mirror the Preferences income-anchor control at the top of the tab.
        context["anchor_income_categories"] = [
            c for c in all_cats if c.direction is Direction.INCOME and c.deleted_at is None
        ]
        context["current_anchor_id"] = preferences_svc.get_income_anchor_category_id(conn, user_id)
    elif active_tab == "fx":
        context["fx_rates"] = fx_repo.list_recent(conn, limit=_FX_LIMIT)
    elif active_tab == "prefs":
        # ADR-0031 §1 — income anchor selector lives here now (was /budget §2b).
        context["income_categories"] = [
            c
            for c in categories_repo.list_all(conn, user_id)
            if c.direction is Direction.INCOME and c.deleted_at is None
        ]
        context["current_anchor_id"] = preferences_svc.get_income_anchor_category_id(conn, user_id)
    # Rising Dough v2 — Settings is a full page (ADR-0051 §7). The template
    # extends base.html and reuses the existing panel fragments.
    hx = request.headers.get("HX-Request") == "true"
    tmpl = "settings/_drawer.html" if hx else "settings/index.html"
    return render(request, tmpl, **context)


@router.get("/close", response_class=HTMLResponse)
def close() -> HTMLResponse:
    """Return an empty fragment so HTMX can swap away the drawer contents."""
    return HTMLResponse("")
