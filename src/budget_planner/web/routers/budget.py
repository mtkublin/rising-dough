"""Budget router (T-036 / T-066; T-R50 removes Plotly per ADR-0054).

The ``/budget`` page stacks:

1. Monthly summary — current month default, month selector top-right.
2. Rules editor — per-category default / recurring(month) / one-off(year, month).
3. Yearly grid — one row per category, 12 months per row.

The historical "Breakdown" section used three Plotly figures; it has been
removed in favour of the Rising Dough v2 Plan hub (``/plan?tab=analytics``)
which renders the same aggregates as pure SVG.

Thin router per ADR-0021: services do the aggregation, the router only shapes
the response.
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.domain.budgets import NewBudgetDefault, NewBudgetOneOffOverride, valid_month
from budget_planner.services import (
    budget_overrides as budget_overrides_service,
    categories as categories_service,
    preferences as preferences_svc,
)
from budget_planner.services.preferences import InvalidAnchorCategoryError
from budget_planner.web import (
    override_dialogs,
    override_forms,
    plan_data,
    plan_redirects,
    plan_year_view,
)
from budget_planner.web.budget_forms import OVERRIDE_YEARS, non_negative_amount
from budget_planner.web.deps import current_user_id, get_db, get_settings_dep
from budget_planner.web.dialogs import dialog_response
from budget_planner.web.errors import not_found_response
from budget_planner.web.htmx import Event, trigger
from budget_planner.web.http_headers import HTML_MEDIA_TYPE
from budget_planner.web.params import MAX_YEAR, MIN_YEAR, parse_int, query_int

router = APIRouter(prefix="/budget", tags=["budget"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/yearly")
def yearly_fragment(request: Request) -> RedirectResponse:
    """The old yearly fragment is retired: the year tab of the Plan hub replaces it (T-UR15a)."""
    return plan_redirects.to_plan(request, "year", {"year": "year"})


@router.get("/rules/{category_id}/overrides/new", response_class=HTMLResponse)
def new_override_form(
    category_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> Response:
    """Override dialog of a category and month, or its remove confirm (``remove=1``).

    ``year`` and ``month`` (the cell or row clicked) and ``tier`` (the scope to open on) come from
    the query; a missing value falls back to today and "this month only".
    """
    cat = categories_service.find_by_id(conn, user_id, category_id)
    if cat is None:
        return not_found_response(request, "category", category_id)
    q = request.query_params
    today = clock.today_local(settings)
    target = plan_year_view.OverrideTarget(
        cat.id,
        cat.name,
        query_int("year", q.get("year"), minimum=MIN_YEAR, maximum=MAX_YEAR) or today.year,
        query_int("month", q.get("month"), minimum=1, maximum=override_forms.MONTHS_IN_YEAR)
        or today.month,
    )
    tier = override_forms.scope(q.get("tier"))
    if q.get("remove") == "1":
        confirm = plan_data.remove_confirm_for(
            conn, user_id, target, tier=tier, currency=settings.base_currency
        )
        return override_dialogs.in_page(
            request,
            dialog_response(request, override_dialogs.REMOVE_TEMPLATE, {"confirm": confirm}),
        )
    dialog = plan_data.override_dialog_for(
        conn, user_id, target, tier=tier, currency=settings.base_currency
    )
    return override_dialogs.in_page(
        request, dialog_response(request, override_dialogs.DIALOG_TEMPLATE, {"override": dialog})
    )


@router.post("/rules/{category_id}/overrides")
def create_override(
    category_id: int,
    request: Request,
    *,
    tier: str = Form(...),
    month: str = Form(""),
    year: str = Form(""),
    amount: str = Form(""),
    remove: str = Form(""),
    origin: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> Response:
    """Save (tier dispatcher, ADR-0031 section 2) or, with ``remove=1``, drop an override."""
    cat = categories_service.find_by_id(conn, user_id, category_id)
    if cat is None:
        return not_found_response(request, "category", category_id)
    shown = override_forms.shown_target(
        cat.id, cat.name, year=year, month=month, today=clock.today_local(settings)
    )
    form = override_dialogs.OverrideForm(tier, month, year, amount, settings.base_currency, origin)
    if remove == "1":
        return override_dialogs.remove(request, conn, user_id, shown, form)
    return override_dialogs.save(request, conn, user_id, shown, form)


@router.get("")
def index(request: Request) -> RedirectResponse:
    """The old Budget page is retired: the budget tab of the Plan hub replaces it (T-UR15a)."""
    return plan_redirects.to_plan(request, "budget", {"year": "year", "month": "month"})


@router.post("/defaults/{category_id}")
def set_default(
    category_id: int,
    request: Request,
    *,
    amount: str = Form(...),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> Response:
    cat = categories_service.find_by_id(conn, user_id, category_id)
    if cat is None:
        return not_found_response(request, "category", category_id)
    minor = non_negative_amount(amount, settings.base_currency)
    if minor is None:
        return Response(status_code=422, content="invalid amount")
    budget_overrides_service.set_default(
        conn, user_id, NewBudgetDefault(category_id=category_id, amount=minor)
    )
    resp = Response(content="ok", media_type=HTML_MEDIA_TYPE)
    trigger(resp, Event.BUDGET_STALE)
    return resp


@router.post("/preferences/income-anchor")
def set_income_anchor(
    category_id: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    """Set or clear the income anchor preference (ADR-0025, F4.7).

    An empty ``category_id`` clears the preference. A numeric value must
    point at a live INCOME-direction category.
    """
    raw = category_id.strip()
    if raw == "":
        preferences_svc.set_income_anchor_category_id(conn, user_id, None)
    else:
        parsed = parse_int(raw)
        if parsed is None:
            return Response(status_code=422, content="invalid category_id")
        try:
            preferences_svc.set_income_anchor_category_id(conn, user_id, parsed)
        except InvalidAnchorCategoryError as err:
            return Response(status_code=422, content=str(err))
    resp = Response(content="ok", media_type=HTML_MEDIA_TYPE)
    trigger(resp, Event.BUDGET_STALE)
    return resp


@router.post("/one-off/{category_id}/{year}/{month}")
def set_one_off(
    category_id: int,
    year: int,
    month: int,
    request: Request,
    *,
    amount: str = Form(...),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> Response:
    cat = categories_service.find_by_id(conn, user_id, category_id)
    if cat is None:
        return not_found_response(request, "category", category_id)
    if not valid_month(month):
        return Response(status_code=422, content="invalid month")
    if year not in OVERRIDE_YEARS:
        return Response(status_code=422, content="invalid year")
    minor = non_negative_amount(amount, settings.base_currency)
    if minor is None:
        return Response(status_code=422, content="invalid amount")
    budget_overrides_service.set_one_off(
        conn,
        user_id,
        NewBudgetOneOffOverride(category_id=category_id, year=year, month=month, amount=minor),
    )
    resp = Response(content="ok", media_type=HTML_MEDIA_TYPE)
    trigger(resp, Event.BUDGET_STALE)
    return resp
