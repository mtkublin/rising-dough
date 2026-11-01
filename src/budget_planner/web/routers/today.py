"""Today router — Rising Dough v2.

Delegates to the existing home router's data assembly, but renders the
v2 Today template (hero + Can-I-afford + Net worth + Upcoming) at the
canonical URL ``/today``. Phase 7 will retire ``/`` → ``/today`` shim.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, Response

from budget_planner.config import Settings
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
)
from budget_planner.services import (
    budget as budget_service,
    fortune as fortune_service,
    today as today_service,
)
from budget_planner.web.deps import get_db, get_settings_dep
from budget_planner.web.rendering import render
from budget_planner.web.routers import home as home_router

router = APIRouter(tags=["today"])


@router.get("/today", response_class=HTMLResponse)
def today(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> HTMLResponse:
    today_d = datetime.now(ZoneInfo(settings.display_timezone)).date()
    # Fiscal cycle anchors the landing month so the hero never pulls a
    # future-cycle budget while spent is still on the previous paycheck
    # (ADR-0064).
    year, month = budget_service.fiscal_month_for(conn, today_d)
    base_ccy = settings.base_currency

    account_rows, totals_by_ccy, fortune_base = home_router._collect_account_rows(conn, base_ccy)
    fortune = fortune_service.compute_fortune(conn, settings)
    summary = budget_service.month_summary(conn, year, month, today=today_d)
    pace = home_router._pace_tag(
        summary.totals.spent_minor, summary.totals.budgeted_minor, today_d, year, month
    )
    days_left = summary.days_until_next_income
    bar_pct = 0
    if summary.totals.budgeted_minor > 0:
        ratio = 100 * summary.totals.spent_minor / summary.totals.budgeted_minor
        bar_pct = max(0, min(100, int(ratio)))

    window_label, window_days = home_router._window_from(request)
    upcoming = home_router._list_upcoming(conn, today_d, window_days)
    categories_by_id = {c.id: c for c in categories_repo.list_all(conn)}
    accounts_by_id = {a.id: a for a in accounts_repo.list_all(conn)}

    return render(
        request,
        "today/index.html",
        today=today_d,
        year=year,
        month=month,
        base_ccy=base_ccy,
        fortune_base=fortune_base,
        fortune=fortune,
        account_rows=account_rows,
        totals_by_ccy=totals_by_ccy,
        summary=summary,
        pace=pace,
        days_left=days_left,
        bar_pct=bar_pct,
        upcoming=upcoming,
        window_label=window_label,
        categories_by_id=categories_by_id,
        accounts_by_id=accounts_by_id,
    )


@router.get("/today/upcoming", response_class=HTMLResponse)
def today_upcoming_fragment(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> HTMLResponse:
    """HTMX fragment for Today's #upcoming-root.

    Returned by inline-promote Esc + after-promote refresh paths so the
    swap preserves the Today surface's row shape (category pill +
    direction-aware amount) instead of falling back to the legacy
    `home/_upcoming_fragment.html` layout.
    """
    today_d = datetime.now(ZoneInfo(settings.display_timezone)).date()
    window_label, window_days = home_router._window_from(request)
    upcoming = home_router._list_upcoming(conn, today_d, window_days)
    categories_by_id = {c.id: c for c in categories_repo.list_all(conn)}
    accounts_by_id = {a.id: a for a in accounts_repo.list_all(conn)}
    return render(
        request,
        "today/_upcoming.html",
        upcoming=upcoming,
        today=today_d,
        window_label=window_label,
        base_ccy=settings.base_currency,
        categories_by_id=categories_by_id,
        accounts_by_id=accounts_by_id,
    )


def _parse_amount_arg(raw: str) -> int | None:
    """Parse the ``amount=`` query arg into minor units.

    The afford input in `today/index.html` is `<input type="number"
    step="0.01">` — users type a MAJOR-unit decimal. Treat every value
    as major units and multiply by 100 to minor. Returns ``None`` on
    invalid input so the router can surface a 422.
    """
    stripped = (raw or "").strip()
    if stripped == "":
        return 0
    try:
        major = float(stripped)
    except (TypeError, ValueError):
        return None
    return round(major * 100)


@router.get("/today/afford", response_class=HTMLResponse)
def afford(
    request: Request,
    amount: str = "",
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> Response:
    """ADR-0056 §3 — HTMX preview for the Can-I-afford input.

    Returns the ``today/_afford_preview.html`` fragment with the recomputed
    per-day figure + signed delta + pace tag. Pure read; no DB write.
    """
    amount_minor = _parse_amount_arg(amount)
    if amount_minor is None or amount_minor < 0:
        return Response(status_code=422, content="invalid amount")
    today_d = datetime.now(ZoneInfo(settings.display_timezone)).date()
    result = today_service.afford(conn, today_d, amount_minor)
    return render(
        request,
        "today/_afford_preview.html",
        result=result,
        amount_minor=amount_minor,
        new_left_per_day=result.per_day_minor,
        delta=result.delta_minor,
        base_ccy=settings.base_currency,
    )


# Alias so the legacy template `/afford` hx-get keeps working during the
# v2 handoff (same handler, same semantics). Phase 7 cleanup drops this.
@router.get("/afford", response_class=HTMLResponse)
def afford_alias(
    request: Request,
    amount: str = "",
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> Response:
    return afford(request, amount, conn, settings)


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
) -> HTMLResponse:
    """Return the unified Add entry overlay (F-04)."""
    tab = next((row for row in _ADD_TAB_FORMS if row[0] == when), _ADD_TAB_FORMS[0])
    active_tab, form_include, action, entity_name = tab
    ctx: dict[str, Any] = {
        "active_tab": active_tab,
        "form_include": form_include,
        "action": action,
        "categories": categories_repo.list_all(conn),
        "accounts": accounts_repo.list_all(conn),
        "errors": {},
        entity_name: None,
    }
    if active_tab == "repeats":
        from budget_planner.web.routers.recurring import (  # noqa: PLC0415
            _EMPTY_TERM_INPUT,
            _formula_source_candidates,
        )

        ctx["source_categories"] = _formula_source_candidates(conn)
        ctx["amount_source"] = "fixed"
        ctx["terms"] = [dict(_EMPTY_TERM_INPUT)]
    return render(request, "partials/_add_entry_overlay.html", **ctx)
