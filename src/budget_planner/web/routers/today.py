"""Today router — Rising Dough v2.

Renders the v2 Today template (hero + Can-I-afford + Net worth + Upcoming)
at the canonical URL ``/today``. ``/`` redirects here (ADR-0077).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.services import (
    accounts as accounts_service,
    budget as budget_service,
    categories as categories_service,
    fortune as fortune_service,
    fx as fx_service,
    today as today_service,
)
from budget_planner.services.recurring_formula import FormulaFx
from budget_planner.web import today_data, view_models
from budget_planner.web.auth_cookies import DEFAULT_LANDING
from budget_planner.web.deps import current_user_id, get_db, get_formula_ctx, get_settings_dep
from budget_planner.web.params import afford_amount_minor
from budget_planner.web.paths import GET_HEAD_METHODS
from budget_planner.web.recurring_forms import EMPTY_TERM_INPUT, formula_source_candidates
from budget_planner.web.rendering import render

router = APIRouter(tags=["today"])


@router.api_route("/", methods=list(GET_HEAD_METHODS), include_in_schema=False)
def root_redirect() -> RedirectResponse:
    """ADR-0077: no home page — ``/`` lands on Today."""
    return RedirectResponse(DEFAULT_LANDING, status_code=303)


@router.get("/today", response_class=HTMLResponse)
def today(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
    fx: FormulaFx = Depends(get_formula_ctx),
) -> HTMLResponse:
    today_d = clock.today_local(settings)
    # Fiscal cycle anchors the landing month so the hero never pulls a
    # future-cycle budget while spent is still on the previous paycheck
    # (ADR-0064).
    year, month = budget_service.fiscal_month_for(conn, user_id, today_d)
    base_ccy, tz = settings.base_currency, settings.display_timezone
    converter = fx_service.converter_for(conn, settings, today_d)
    account_rows, totals_by_ccy = today_data.collect_account_rows(conn, user_id, converter)
    fortune = fortune_service.compute_fortune(conn, user_id, converter)
    summary = budget_service.month_summary(
        conn, user_id, year, month, today=today_d, base_currency=base_ccy, display_timezone=tz
    )
    pace = today_data.pace_tag(
        summary.totals.spent_minor, summary.totals.budgeted_minor, today_d, year, month
    )
    budget = view_models.budget_view(summary, today_d)

    window_label, window_days = today_data.window_from(request)
    upcoming = today_data.list_upcoming(conn, user_id, today_d, window_days, fx)
    categories_by_id = {c.id: c for c in categories_service.list_all(conn, user_id)}
    accounts_by_id = {a.id: a for a in accounts_service.list_all(conn, user_id)}

    return render(
        request,
        "today/index.html",
        today=today_d,
        year=year,
        month=month,
        base_ccy=base_ccy,
        fortune_base=fortune.net_base,
        fortune=fortune,
        account_rows=account_rows,
        totals_by_ccy=totals_by_ccy,
        budget=budget,
        pace=pace,
        upcoming_view=view_models.upcoming_view(
            upcoming, today_d, categories_by_id, accounts_by_id
        ),
        window_label=window_label,
        categories_by_id=categories_by_id,
        accounts_by_id=accounts_by_id,
    )


@router.get("/today/upcoming", response_class=HTMLResponse)
def today_upcoming_fragment(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
    fx: FormulaFx = Depends(get_formula_ctx),
) -> HTMLResponse:
    """HTMX fragment for Today's #upcoming-root.

    Returned by inline-promote Esc + after-promote refresh paths so the
    swap preserves the Today surface's row shape (category pill +
    direction-aware amount) instead of a generic list layout.
    """
    today_d = clock.today_local(settings)
    window_label, window_days = today_data.window_from(request)
    upcoming = today_data.list_upcoming(conn, user_id, today_d, window_days, fx)
    categories_by_id = {c.id: c for c in categories_service.list_all(conn, user_id)}
    accounts_by_id = {a.id: a for a in accounts_service.list_all(conn, user_id)}
    return render(
        request,
        "today/_upcoming.html",
        upcoming_view=view_models.upcoming_view(
            upcoming, today_d, categories_by_id, accounts_by_id
        ),
        today=today_d,
        window_label=window_label,
        base_ccy=settings.base_currency,
        categories_by_id=categories_by_id,
        accounts_by_id=accounts_by_id,
    )


@router.get("/today/afford", response_class=HTMLResponse)
def afford(
    request: Request,
    amount: str = "",
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> Response:
    """ADR-0056 §3 — HTMX preview for the Can-I-afford input.

    Returns the ``today/_afford_preview.html`` fragment with the recomputed
    per-day figure + signed delta + pace tag. Pure read; no DB write.
    """
    amount_minor = afford_amount_minor(amount, settings.base_currency)
    if amount_minor is None or amount_minor < 0:
        return Response(status_code=422, content="invalid amount")
    today_d = clock.today_local(settings)
    result = today_service.afford(
        conn,
        user_id,
        today_d,
        amount_minor,
        base_currency=settings.base_currency,
        display_timezone=settings.display_timezone,
    )
    return render(
        request,
        "today/_afford_preview.html",
        result=result,
        amount_minor=amount_minor,
        new_left_per_day=result.per_day_minor,
        delta=result.delta_minor,
        base_ccy=settings.base_currency,
    )


# F-04 — Unified Add entry overlay. Hosts the Happened / Planned / Repeats
# segmented control; each tab reuses the existing /transactions, /planned,
# /recurring form partials so submit paths stay unchanged.
_ADD_TAB_FORMS: tuple[tuple[str, str, str, str], ...] = (
    ("happened", "partials/transactions/_form.html", "/transactions", "txn"),
    ("planned", "partials/planned/_form.html", "/planned", "planned"),
    ("repeats", "partials/recurring/_form.html", "/recurring", "rule"),
)


@router.get("/add", response_class=HTMLResponse)
def add_entry_overlay(
    request: Request,
    when: str = "happened",
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    """Return the unified Add entry overlay (F-04)."""
    tab = next((row for row in _ADD_TAB_FORMS if row[0] == when), _ADD_TAB_FORMS[0])
    active_tab, form_include, action, entity_name = tab
    ctx: dict[str, Any] = {
        "active_tab": active_tab,
        "form_include": form_include,
        "action": action,
        "categories": categories_service.list_all(conn, user_id),
        "accounts": accounts_service.list_all(conn, user_id),
        "errors": {},
        entity_name: None,
    }
    if active_tab == "repeats":
        ctx["source_categories"] = formula_source_candidates(conn, user_id)
        ctx["amount_source"] = "fixed"
        ctx["terms"] = [dict(EMPTY_TERM_INPUT)]
    return render(request, "partials/_add_entry_overlay.html", **ctx)
