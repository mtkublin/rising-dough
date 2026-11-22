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
from budget_planner.services import (
    accounts as accounts_service,
    categories as categories_service,
    planned as planned_service,
    transactions as transactions_service,
)
from budget_planner.web import ledger_data
from budget_planner.web.deps import current_user_id, get_db, get_settings_dep, get_today
from budget_planner.web.ledger_types import coerce_view
from budget_planner.web.paths import LEDGER_PATH, TABLE_PATH
from budget_planner.web.rendering import render, render_context

router = APIRouter(prefix=LEDGER_PATH, tags=["ledger"])


@router.get("", response_class=HTMLResponse)
def index(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
    today: date = Depends(get_today),
) -> HTMLResponse:
    view = coerce_view(request.query_params.get("view"))
    filters = ledger_data.parse_filters(request)
    ctx = ledger_data.index_context(
        conn, user_id, settings=settings, view=view, filters=filters, today=today
    )
    return render_context(request, "ledger/index.html", ctx)


@router.get(TABLE_PATH, response_class=HTMLResponse)
def table_fragment(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
    today: date = Depends(get_today),
) -> HTMLResponse:
    view = coerce_view(request.query_params.get("view"))
    ctx = ledger_data.table_context(
        conn,
        user_id,
        settings=settings,
        view=view,
        filters=ledger_data.parse_filters(request),
        today=today,
    )
    return render_context(request, "ledger/_table.html", ctx)


@router.get("/recently-deleted", response_class=HTMLResponse)
def recently_deleted(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    """T-R70 — list soft-deleted transactions, planned, and categories (90-day cutoff).

    ADR-0019 (soft delete + audit); ADR-0022 (archived categories).
    """
    txns = transactions_service.list_recently_deleted(conn, user_id, days=90)
    planned_items = planned_service.list_recently_deleted(conn, user_id, days=90)
    cats = categories_service.list_recently_deleted(conn, user_id, days=90)
    accounts_by_id = {a.id: a for a in accounts_service.list_all(conn, user_id)}
    categories_by_id = {c.id: c for c in categories_service.list_all(conn, user_id)}
    return render(
        request,
        "ledger/_recently_deleted.html",
        txns=txns,
        planned_items=planned_items,
        categories=cats,
        accounts_by_id=accounts_by_id,
        categories_by_id=categories_by_id,
    )
