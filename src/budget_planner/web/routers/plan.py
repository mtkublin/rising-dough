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
from budget_planner.web import plan_data
from budget_planner.web.deps import current_user_id, get_db, get_settings_dep
from budget_planner.web.params import query_choice, query_int, require_year_month
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
    tab_norm: PlanTab = query_choice("tab", tab, _VALID) or "budget"
    today_d = clock.today_local(settings)
    month_scoped = tab_norm in {"budget", "analytics"}
    query = request.query_params if month_scoped else {}
    require_year_month(request.query_params.get("year"), query.get("month"))
    picked = budget_service.resolve_picker_month(
        conn, user_id, today_d, year_raw=query.get("year"), month_raw=query.get("month")
    )
    ctx: dict[str, Any] = plan_data.base_context(tab_norm, today_d, settings.base_currency, picked)
    if tab_norm == "budget":
        budget = plan_data.budget_view_for(conn, user_id, picked, today_d, settings)
        ctx["budget"] = budget
        ctx["period"] = plan_data.budget_period_for(picked, budget)
        return render(request, "pages/plan/budget.html", nav_current="plan", **ctx)
    if tab_norm == "year":
        year_raw = request.query_params.get("year")
        ctx.update(plan_data.year_context(conn, user_id, today_d, year_raw, settings=settings))
    elif tab_norm == "forecast":
        requested = query_int(
            "horizon", request.query_params.get("horizon"), choices=_FORECAST_HORIZON_CHOICES
        )
        horizon = forecast_service.normalize_horizon(
            None if requested is None else str(requested), _FORECAST_HORIZON_CHOICES
        )
        ctx["forecast"] = plan_data.forecast_page_for(
            conn, user_id, settings, today_d, horizon=horizon, choices=_FORECAST_HORIZON_CHOICES
        )
        return render(request, "pages/plan/forecast.html", nav_current="plan", **ctx)
    else:
        ctx["analytics"] = plan_data.analytics_page_for(
            conn, user_id, picked, request.query_params.get("period"), settings=settings
        )
        return render(request, "pages/plan/analytics.html", nav_current="plan", **ctx)
    return render(request, "plan/index.html", **ctx)
