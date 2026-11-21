"""Plan hub — Rising Dough v2 (ADR-0051 §5).

Renders a tabbed shell (Budget · Year · Forecast · Analytics) with the
period header above tabs. Each tab assembles data from the existing
service helpers and renders a v2 template.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Any, Literal, TypedDict
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from budget_planner.config import Settings
from budget_planner.services import (
    analytics as analytics_service,
    budget as budget_service,
    forecast as forecast_service,
)
from budget_planner.web import charts, plan_data
from budget_planner.web.deps import current_user_id, get_db, get_settings_dep
from budget_planner.web.rendering import render

router = APIRouter(tags=["plan"])

PlanTab = Literal["budget", "year", "forecast", "analytics"]
_VALID: tuple[PlanTab, ...] = ("budget", "year", "forecast", "analytics")

_FORECAST_HORIZON_CHOICES: tuple[int, ...] = (6, 12, 24, 60)
_MINOR_UNITS_PER_MAJOR = 100.0


class AnalyticsCharts(TypedDict):
    spend_chart: charts.HorizontalBarsChart
    flow_chart: charts.GroupedBarsChart


def _analytics_charts(bundle: analytics_service.AnalyticsBundle) -> AnalyticsCharts:
    """Compute SVG geometry for the Analytics tab charts.

    Returns a dict with ``spend_chart`` (horizontal bars) and ``flow_chart``
    (grouped bars) so the template can render inline SVG without doing any
    math itself. All amounts converted to major units for display.
    """
    spend_items = tuple(
        (row.category_name, row.amount_minor / _MINOR_UNITS_PER_MAJOR)
        for row in bundle.spend_by_category
    )
    flow_groups = tuple(
        {
            "label": point.label[-5:],  # YYYY-MM → MM-?; keep tail for density
            "bars": [
                ("income", point.income_minor / _MINOR_UNITS_PER_MAJOR),
                ("expense", point.expense_minor / _MINOR_UNITS_PER_MAJOR),
            ],
        }
        for point in bundle.income_vs_expense_monthly
    )
    return AnalyticsCharts(
        spend_chart=charts.horizontal_bars(spend_items),
        flow_chart=charts.grouped_bars(flow_groups),
    )


@router.get("/plan", response_class=HTMLResponse)
def plan(
    request: Request,
    tab: str = "budget",
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    tab_norm: PlanTab = tab if tab in _VALID else "budget"
    today_d = datetime.now(ZoneInfo(settings.display_timezone)).date()
    month_scoped = tab_norm in {"budget", "analytics"}
    query = request.query_params if month_scoped else {}
    picked = budget_service.resolve_picker_month(
        conn, user_id, today_d, year_raw=query.get("year"), month_raw=query.get("month")
    )
    ctx: dict[str, Any] = plan_data.base_context(tab_norm, today_d, settings.base_currency, picked)
    if tab_norm == "budget":
        ctx["summary"] = budget_service.month_summary_for_picker(conn, user_id, picked, today_d)
    elif tab_norm == "year":
        ctx.update(plan_data.year_context(conn, user_id, today_d, request.query_params.get("year")))
    elif tab_norm == "forecast":
        horizon = forecast_service.normalize_horizon(
            request.query_params.get("horizon"), _FORECAST_HORIZON_CHOICES
        )
        projection = forecast_service.monthly_projection(
            conn, user_id, settings, today_d, horizon=horizon
        )
        ctx.update(
            forecast_points=projection,
            forecast_horizon=horizon,
            forecast_horizon_choices=_FORECAST_HORIZON_CHOICES,
            forecast_chart=charts.line_area(
                tuple((float(i), p.value_major) for i, p in enumerate(projection)),
                x_labels=tuple(p.label for p in projection),
            ),
            forecast_summary=forecast_service.projection_summary(projection),
        )
    else:
        bundle, derived = plan_data.analytics_bundle(
            conn, user_id, today_d, picked, request.query_params.get("period")
        )
        ctx.update(derived, **_analytics_charts(bundle))
    return render(request, "plan/index.html", **ctx)


@router.get("/plan/analytics", response_class=HTMLResponse)
def plan_analytics(
    request: Request,
    period: str = "month",
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    """ADR-0056 §6 — four-panel analytics bundle for the Analytics tab.

    ``period`` controls spend-by-category + largest-items window; the
    averages + flow trend always span the trailing 12 months.
    """
    period_norm = analytics_service.normalize_period(period)
    today_d = datetime.now(ZoneInfo(settings.display_timezone)).date()
    data = analytics_service.bundle(conn, user_id, today=today_d, period=period_norm)
    return render(
        request,
        "plan/_analytics_bundle.html",
        bundle=data,
        base_ccy=settings.base_currency,
        period=period_norm,
        **_analytics_charts(data),
    )


@router.get("/budget-legacy", include_in_schema=False)
def _redirect_budget() -> RedirectResponse:
    return RedirectResponse(url="/plan?tab=budget", status_code=302)
