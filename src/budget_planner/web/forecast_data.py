"""Template-context assembly for the Forecast page (T-037, T-Q265).

Clamps the requested horizon, asks the forecast service for the monthly series
and builds the server-rendered SVG chart. No business logic.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from typing import Final

from budget_planner.config import Settings
from budget_planner.services import forecast as forecast_service
from budget_planner.web import charts

DEFAULT_HORIZON_MONTHS: Final = 12
MIN_HORIZON_MONTHS: Final = 1
MAX_HORIZON_MONTHS: Final = 60
_MONTH_LABEL_FORMAT: Final = "%b %Y"


@dataclass(frozen=True, slots=True)
class ForecastView:
    """Everything the Forecast page and its fragment render."""

    horizon_months: int
    monthly: forecast_service.MonthlySeries
    chart: charts.LineAreaChart


def clamp_horizon(requested: int | None) -> int:
    """Requested horizon in months, defaulted when absent and clamped to the allowed range."""
    if requested is None:
        return DEFAULT_HORIZON_MONTHS
    return max(MIN_HORIZON_MONTHS, min(requested, MAX_HORIZON_MONTHS))


def build_view(
    conn: sqlite3.Connection,
    user_id: int,
    settings: Settings,
    today: date,
    requested_horizon: int | None,
) -> ForecastView:
    """Forecast series plus its chart for the (clamped) horizon."""
    horizon_months = clamp_horizon(requested_horizon)
    monthly = forecast_service.monthly_for_settings(conn, user_id, settings, today, horizon_months)
    chart = charts.line_area_minor(
        tuple(m.end_balance_base_minor for m in monthly.months),
        settings.base_currency,
        tuple(m.month.strftime(_MONTH_LABEL_FORMAT) for m in monthly.months),
    )
    return ForecastView(horizon_months=horizon_months, monthly=monthly, chart=chart)
