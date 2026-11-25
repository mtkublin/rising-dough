"""Today router — Rising Dough v2.

Renders the v2 Today template (hero + Can-I-afford + Net worth + Upcoming)
at the canonical URL ``/today``. ``/`` redirects here (ADR-0077).
"""

from __future__ import annotations

import sqlite3

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
from budget_planner.web import entry_forms, form_responses, today_data, view_models
from budget_planner.web.auth_cookies import DEFAULT_LANDING
from budget_planner.web.deps import current_user_id, get_db, get_formula_fx, get_settings_dep
from budget_planner.web.http_headers import HX_RESWAP, HX_RETARGET
from budget_planner.web.params import query_choice
from budget_planner.web.paths import GET_HEAD_METHODS
from budget_planner.web.rendering import render

router = APIRouter(tags=["today"])


@router.api_route("/", methods=list(GET_HEAD_METHODS), include_in_schema=False)
def root_redirect() -> RedirectResponse:
    """ADR-0077: no home page — ``/`` lands on Today."""
    return RedirectResponse(DEFAULT_LANDING, status_code=303)


@router.get("/today", response_class=HTMLResponse)
def today(
    request: Request,
    amount: str = "",
    *,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
    fx: FormulaFx = Depends(get_formula_fx),
) -> HTMLResponse:
    today_d = clock.today_local(settings)
    # Fiscal cycle anchors the landing month so the hero never pulls a
    # future-cycle budget while spent is still on the previous paycheck
    # (ADR-0064).
    year, month = budget_service.fiscal_month_for(conn, user_id, today_d)
    base_ccy, tz = settings.base_currency, settings.display_timezone
    converter = fx_service.converter_for(conn, settings, today_d)
    account_rows, _ = today_data.collect_account_rows(conn, user_id, converter)
    fortune = fortune_service.compute_fortune(conn, user_id, converter)
    summary = budget_service.month_summary(
        conn, user_id, year, month, today=today_d, base_currency=base_ccy, display_timezone=tz
    )
    pace = today_data.pace_tag(
        summary.totals.spent_minor, summary.totals.budgeted_minor, today_d, year, month
    )
    budget = view_models.budget_view(summary, today_d)
    afford_state = today_data.afford_state(
        conn, user_id, today_d, amount, base_currency=base_ccy, display_timezone=tz
    )

    window_label, window_days = today_data.window_from(request)
    upcoming = today_data.list_upcoming(conn, user_id, today_d, window_days, fx)
    categories_by_id = {c.id: c for c in categories_service.list_all(conn, user_id)}
    accounts_by_id = {a.id: a for a in accounts_service.list_all(conn, user_id)}

    return render(
        request,
        "pages/today/index.html",
        nav_current="today",
        view=today_data.today_view(budget, pace, fortune, len(account_rows), base_ccy),
        afford=today_data.afford_panel(afford_state, base_ccy),
        upcoming=today_data.today_upcoming(
            upcoming,
            today_d,
            categories_by_id,
            accounts_by_id,
            base_currency=base_ccy,
            window_label=window_label,
        ),
        window_label=window_label,
    )


@router.get("/today/upcoming", response_class=HTMLResponse)
def today_upcoming_fragment(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
    fx: FormulaFx = Depends(get_formula_fx),
) -> HTMLResponse:
    """HTMX fragment ``today/upcoming-list``: the list body for the chosen window.

    Swapped in by the range control and after a promote, skip or batch promote
    (``today-stale``).
    """
    today_d = clock.today_local(settings)
    window_label, window_days = today_data.window_from(request)
    upcoming = today_data.list_upcoming(conn, user_id, today_d, window_days, fx)
    categories_by_id = {c.id: c for c in categories_service.list_all(conn, user_id)}
    accounts_by_id = {a.id: a for a in accounts_service.list_all(conn, user_id)}
    return render(
        request,
        "fragments/today/upcoming-list.html",
        upcoming=today_data.today_upcoming(
            upcoming,
            today_d,
            categories_by_id,
            accounts_by_id,
            base_currency=settings.base_currency,
            window_label=window_label,
        ),
        window_label=window_label,
    )


@router.get("/today/afford", response_class=HTMLResponse)
def afford(
    request: Request,
    amount: str = "",
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> Response:
    """ADR-0056 §3: HTMX preview for the Can-I-afford input.

    Returns the ``today/afford-result`` fragment with the recomputed per-day figure
    and delta (or the over line). Pure read; no DB write. An invalid amount is a 422
    whose body is the message; HTMX puts it into the result output.
    """
    state = today_data.afford_state(
        conn,
        user_id,
        clock.today_local(settings),
        amount,
        base_currency=settings.base_currency,
        display_timezone=settings.display_timezone,
    )
    if state.result is None:
        return Response(
            status_code=422,
            content=today_service.AFFORD_INVALID_MESSAGE,
            headers={HX_RETARGET: "#afford-result", HX_RESWAP: "innerHTML"},
        )
    return render(
        request,
        "fragments/today/afford-result.html",
        afford=today_data.afford_panel(state, settings.base_currency),
    )


@router.get("/add", response_class=HTMLResponse)
def add_entry_overlay(
    request: Request,
    *,
    when: str = "happened",
    dialog: str = "",
    hero: str = "",
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
    fx: FormulaFx = Depends(get_formula_fx),
) -> Response:
    """The new-entry dialog (happened / planned / repeats tab, T-UR07b).

    ``hero=1`` re-renders the dialog from the form's values for the hero refresh (account, category,
    amount source); the caller swaps only ``.rd-dialog__hero``.

    ``dialog=1`` is the new shell's ask; the old shell's "+ Add" (ledger, forecast, settings) still
    gets the slide-over until those pages are ported (T-UR09, T-UR10).
    """
    tab = query_choice("when", when, entry_forms.ENTRY_TABS) or "happened"
    if not dialog:
        return form_responses.open_legacy_overlay(request, conn, user_id, tab=tab)
    if hero:
        return form_responses.new_entry_hero(request, conn, user_id, tab=tab, fx=fx)
    return form_responses.open_new_entry(request, conn, user_id, tab=tab)
