"""Plan hub — Rising Dough v2 (ADR-0051 §5).

Renders a tabbed shell (Budget · Year · Forecast · Analytics) with the
period header above tabs. Each tab assembles data from the existing
service helpers and renders a v2 template.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.services import budget as budget_service, forecast as forecast_service
from budget_planner.web import charts, plan_data, view_models
from budget_planner.web.deps import current_user_id, get_db, get_settings_dep
from budget_planner.web.rendering import render

router = APIRouter(tags=["plan"])

PlanTab = Literal["budget", "year", "forecast", "analytics"]
_VALID: tuple[PlanTab, ...] = ("budget", "year", "forecast", "analytics")

_FORECAST_HORIZON_CHOICES: tuple[int, ...] = (6, 12, 24, 60)


@router.get("/plan", response_class=HTMLResponse)
def plan(
    request: Request,
    tab: str = "budget",
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    tab_norm: PlanTab = tab if tab in _VALID else "budget"
    today_d = clock.today_local(settings)
    month_scoped = tab_norm in {"budget", "analytics"}
    query = request.query_params if month_scoped else {}
    picked = budget_service.resolve_picker_month(
        conn, user_id, today_d, year_raw=query.get("year"), month_raw=query.get("month")
    )
    ctx: dict[str, Any] = plan_data.base_context(tab_norm, today_d, settings.base_currency, picked)
    if tab_norm == "budget":
        summary = budget_service.month_summary_for_picker(
            conn, user_id, picked, today_d, base_currency=settings.base_currency
        )
        ctx["budget"] = view_models.budget_view(summary, today_d)
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
            conn, user_id, picked, request.query_params.get("period"), settings=settings
        )
        ctx.update(derived)
        ctx["spend_chart"], ctx["flow_chart"] = charts.analytics_charts(
            bundle, settings.base_currency
        )
    return render(request, "plan/index.html", **ctx)
