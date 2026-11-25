"""Ledger router (T-064, T-Q265).

Unifies ``/transactions``, ``/planned``, and ``/recurring`` behind a single
``/ledger`` page + ``/ledger/table`` fragment with a ``view`` query parameter.
Parse, call, render: the data assembly lives in ``web/ledger_data.py``.
See ADR-0023 for the information-architecture decision.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from budget_planner.config import Settings
from budget_planner.web import ledger_data
from budget_planner.web.deps import current_user_id, get_db, get_settings_dep, get_today
from budget_planner.web.ledger_types import query_view
from budget_planner.web.paths import LEDGER_PATH, TABLE_PATH
from budget_planner.web.rendering import render_context

router = APIRouter(prefix=LEDGER_PATH, tags=["ledger"])


@router.get("", response_class=HTMLResponse)
def index(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
    today: date = Depends(get_today),
) -> HTMLResponse:
    view = query_view(request.query_params.get("view"))
    filters = ledger_data.parse_filters(request)
    ctx = ledger_data.index_context(
        conn, user_id, settings=settings, view=view, filters=filters, today=today
    )
    return render_context(request, "pages/ledger/index.html", ctx)


@router.get(TABLE_PATH, response_class=HTMLResponse)
def table_fragment(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
    today: date = Depends(get_today),
) -> HTMLResponse:
    view = query_view(request.query_params.get("view"))
    return ledger_data.render_table_for(
        request, conn, user_id, settings=settings, view=view, today=today
    )


@router.get("/recently-deleted", response_class=HTMLResponse)
def recently_deleted(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    """T-R70 — list soft-deleted transactions, planned, and categories (90-day cutoff).

    ADR-0019 (soft delete + audit); ADR-0022 (archived categories).
    """
    ctx = ledger_data.deleted_context(conn, user_id, settings)
    return render_context(request, "pages/ledger/recently-deleted.html", ctx)
