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
from fastapi.responses import HTMLResponse, Response

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.domain.budgets import NewBudgetDefault, NewBudgetOneOffOverride
from budget_planner.services import (
    budget as budget_service,
    budget_overrides as budget_overrides_service,
    budget_rules,
    categories as categories_service,
    preferences as preferences_svc,
)
from budget_planner.services.preferences import InvalidAnchorCategoryError
from budget_planner.web import view_models
from budget_planner.web.budget_forms import non_negative_amount, parse_override, valid_month
from budget_planner.web.deps import current_user_id, get_db, get_settings_dep, today_for
from budget_planner.web.htmx import trigger
from budget_planner.web.params import MAX_YEAR, MIN_YEAR, parse_int, parse_year_month
from budget_planner.web.rendering import render

router = APIRouter(prefix="/budget", tags=["budget"])

_MONTHS_IN_YEAR = 12


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/yearly", response_class=HTMLResponse)
def yearly_fragment(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    """HTMX fragment for the Yearly grid (ADR-0031 §3).

    Returns just the ``#budget-yearly`` section so year switching does not
    force a full-page reload.
    """
    q = request.query_params
    today = clock.today_local(settings)
    year, _ = parse_year_month(q.get("year"), None, (today.year, 1))
    yearly = budget_service.yearly_grid(conn, user_id, year)
    return render(
        request,
        "budget/_yearly.html",
        year=year,
        yearly=yearly,
        month_labels=view_models.MONTH_SHORT,
        base_ccy=settings.base_currency,
    )


@router.get("/rules/{category_id}/overrides/new", response_class=HTMLResponse)
def new_override_form(
    category_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    """Slide-over form for creating a recurring / one-off override (ADR-0031 §2).

    Optional ``month`` / ``year`` query params prefill the fields when the
    form is opened from the Year heatmap (ADR-0051 §5.3).
    """
    cat = categories_service.find_by_id(conn, user_id, category_id)
    tz_now = clock.today_local(settings)
    q = request.query_params
    preset_month = parse_int(q.get("month"), minimum=1, maximum=_MONTHS_IN_YEAR)
    preset_year = parse_int(q.get("year"), minimum=MIN_YEAR, maximum=MAX_YEAR)
    period = view_models.override_period(preset_month or tz_now.month, preset_year or tz_now.year)
    if cat is None:
        return render(
            request,
            "partials/budget/_override_form.html",
            category=None,
            errors={"category": "not found"},
            period=period,
            status_code=404,
        )
    default_row = budget_overrides_service.get_default(conn, user_id, category_id)
    inline = q.get("inline") == "1"
    if inline:
        return render(
            request,
            "partials/budget/_override_form.html",
            category=cat,
            errors={},
            inline=True,
            period=period,
            default_amount_minor=default_row.amount if default_row else None,
        )
    return render(
        request,
        "partials/_slideover.html",
        slide_over_title=f"Override · {cat.name}",
        form_include="partials/budget/_override_form.html",
        category=cat,
        errors={},
        period=period,
        default_amount_minor=default_row.amount if default_row else None,
    )


@router.post("/rules/{category_id}/overrides")
def create_override(
    category_id: int,
    *,
    tier: str = Form(...),
    month: str = Form(""),
    year: str = Form(""),
    amount: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> Response:
    """Tier-dispatcher for the Override slide-over (ADR-0031 section 2)."""
    cat = categories_service.find_by_id(conn, user_id, category_id)
    if cat is None:
        return Response(status_code=404, content="not found")
    parsed = parse_override(
        category_id,
        tier=tier,
        month=month,
        year=year,
        amount=amount,
        currency=settings.base_currency,
    )
    if parsed.command is None:
        return Response(status_code=422, content=parsed.error)
    budget_rules.apply_override(conn, user_id, parsed.command)
    resp = Response(content="ok", media_type="text/html")
    trigger(resp, "budget-stale")
    return resp


@router.get("", response_class=HTMLResponse)
def index(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    q = request.query_params
    # Default landing month = fiscal cycle (ADR-0064); overridable via query.
    fiscal = budget_service.fiscal_month_for(conn, user_id, today_for(request))
    year, month = parse_year_month(q.get("year"), q.get("month"), fiscal)
    today = clock.today_local(settings)
    summary = budget_service.month_summary(conn, user_id, year, month, today=today)
    return render(
        request,
        "budget/index.html",
        year=year,
        month=month,
        budget=view_models.budget_view(summary, today),
        period_label=view_models.period_label(year, month),
        month_options=view_models.month_options(month),
        rules=budget_rules.rules_rows(conn, user_id),
        yearly=budget_service.yearly_grid(conn, user_id, year),
        month_labels=view_models.MONTH_SHORT,
        base_ccy=settings.base_currency,
    )


@router.post("/defaults/{category_id}")
def set_default(
    category_id: int,
    amount: str = Form(...),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> Response:
    cat = categories_service.find_by_id(conn, user_id, category_id)
    if cat is None:
        return Response(status_code=404, content="not found")
    minor = non_negative_amount(amount, settings.base_currency)
    if minor is None:
        return Response(status_code=422, content="invalid amount")
    budget_overrides_service.set_default(
        conn, user_id, NewBudgetDefault(category_id=category_id, amount=minor)
    )
    resp = Response(content="ok", media_type="text/html")
    trigger(resp, "budget-stale")
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
    resp = Response(content="ok", media_type="text/html")
    trigger(resp, "budget-stale")
    return resp


@router.post("/one-off/{category_id}/{year}/{month}")
def set_one_off(
    category_id: int,
    year: int,
    month: int,
    *,
    amount: str = Form(...),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> Response:
    cat = categories_service.find_by_id(conn, user_id, category_id)
    if cat is None:
        return Response(status_code=404, content="not found")
    if not valid_month(month):
        return Response(status_code=422, content="invalid month")
    minor = non_negative_amount(amount, settings.base_currency)
    if minor is None:
        return Response(status_code=422, content="invalid amount")
    budget_overrides_service.set_one_off(
        conn,
        user_id,
        NewBudgetOneOffOverride(category_id=category_id, year=year, month=month, amount=minor),
    )
    resp = Response(content="ok", media_type="text/html")
    trigger(resp, "budget-stale")
    return resp
