"""Forecast router (T-037, ADR-0043; T-R50 removes Plotly per ADR-0054).

The user-facing horizon is specified in **months** (ADR-0043) and expanded
to days at the router boundary so the pure daily projection service stays
unchanged. Chart granularity is monthly: one point per month at EOM.

Charts are now server-rendered SVG via :mod:`budget_planner.web.charts`
(ADR-0054); Plotly has been removed.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from budget_planner.config import Settings
from budget_planner.services import forecast as forecast_service
from budget_planner.web import charts
from budget_planner.web.deps import current_user_id, get_db, get_settings_dep
from budget_planner.web.rendering import render

router = APIRouter(prefix="/forecast", tags=["forecast"])

_DEFAULT_HORIZON_MONTHS = 12
_MIN_HORIZON_MONTHS = 1
_MAX_HORIZON_MONTHS = 60
_MINOR_UNITS_PER_MAJOR = 100.0


def _parse_horizon_months(request: Request) -> int:
    try:
        val = int(request.query_params.get("horizon_months", _DEFAULT_HORIZON_MONTHS))
    except (TypeError, ValueError):
        return _DEFAULT_HORIZON_MONTHS
    return max(_MIN_HORIZON_MONTHS, min(val, _MAX_HORIZON_MONTHS))


def _compute(
    conn: sqlite3.Connection,
    user_id: int,
    settings: Settings,
    horizon_months: int,
) -> forecast_service.MonthlySeries:
    today = date.today()  # noqa: DTZ011
    with httpx.Client(timeout=5.0) as client:
        return forecast_service.forecast_monthly(
            conn, user_id, client, today, horizon_months, settings.base_currency
        )


def _series_to_chart(monthly: forecast_service.MonthlySeries) -> charts.LineAreaChart:
    points = tuple(
        (float(i), m.end_balance_base_minor / _MINOR_UNITS_PER_MAJOR)
        for i, m in enumerate(monthly.months)
    )
    labels = tuple(m.month.strftime("%b %Y") for m in monthly.months)
    return charts.line_area(points, x_labels=labels)


@router.get("", response_class=HTMLResponse)
def index(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    horizon_months = _parse_horizon_months(request)
    monthly = _compute(conn, user_id, settings, horizon_months)
    chart = _series_to_chart(monthly)
    return render(
        request,
        "forecast/index.html",
        horizon_months=horizon_months,
        monthly=monthly,
        chart=chart,
    )


@router.get("/view", response_class=HTMLResponse)
def view_fragment(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    horizon_months = _parse_horizon_months(request)
    monthly = _compute(conn, user_id, settings, horizon_months)
    chart = _series_to_chart(monthly)
    return render(
        request,
        "partials/forecast/_view.html",
        chart=chart,
        monthly=monthly,
        horizon_months=horizon_months,
    )
