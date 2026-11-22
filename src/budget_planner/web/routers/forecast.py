"""Forecast router (T-037, ADR-0043; T-R50 removes Plotly per ADR-0054).

The user-facing horizon is specified in **months** (ADR-0043) and expanded
to days inside the forecast service so the pure daily projection stays
unchanged. Chart granularity is monthly: one point per month at EOM.
Parse, call, render: the chart and context assembly lives in ``web/forecast_data.py``.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from budget_planner.config import Settings
from budget_planner.web import forecast_data
from budget_planner.web.deps import current_user_id, get_db, get_settings_dep, get_today
from budget_planner.web.params import query_int
from budget_planner.web.rendering import render

router = APIRouter(prefix="/forecast", tags=["forecast"])


@router.get("", response_class=HTMLResponse)
def index(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
    today: date = Depends(get_today),
) -> HTMLResponse:
    horizon = query_int("horizon_months", request.query_params.get("horizon_months"))
    v = forecast_data.build_view(conn, user_id, settings, today, horizon)
    return render(
        request,
        "forecast/index.html",
        horizon_months=v.horizon_months,
        monthly=v.monthly,
        chart=v.chart,
    )


@router.get("/view", response_class=HTMLResponse)
def view_fragment(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
    today: date = Depends(get_today),
) -> HTMLResponse:
    horizon = query_int("horizon_months", request.query_params.get("horizon_months"))
    v = forecast_data.build_view(conn, user_id, settings, today, horizon)
    return render(
        request,
        "partials/forecast/_view.html",
        horizon_months=v.horizon_months,
        monthly=v.monthly,
        chart=v.chart,
    )
