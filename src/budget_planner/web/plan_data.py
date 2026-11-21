"""Template-context assembly for the Plan hub (ADR-0051 section 5, ADR-0138).

No business logic: services compute, this module only names the template keys.
"""

from __future__ import annotations

import sqlite3
from datetime import date

from budget_planner.services import analytics as analytics_service, budget as budget_service
from budget_planner.services.analytics import AnalyticsBundle
from budget_planner.web import view_models


def base_context(
    tab: str, today: date, base_ccy: str, picked: budget_service.PickerMonth
) -> dict[str, object]:
    """Return the keys every Plan tab shares: selected month and its neighbours."""
    return {
        "tab": tab,
        "header": view_models.plan_header(tab, picked.year, picked.month),
        "today": today,
        "year": picked.year,
        "month": picked.month,
        "base_ccy": base_ccy,
        "period_prev_year": picked.prev_year,
        "period_prev_month": picked.prev_month,
        "period_next_year": picked.next_year,
        "period_next_month": picked.next_month,
    }


def year_context(
    conn: sqlite3.Connection, user_id: int, today: date, year_raw: str | None
) -> dict[str, object]:
    """Return the Year tab keys for the requested (or fiscal) year."""
    selected = budget_service.resolve_picker_month(conn, user_id, today, year_raw=year_raw).year
    rows = budget_service.yearly_grid(conn, user_id, selected)
    column_totals, grand_total = budget_service.yearly_grid_totals(rows)
    return {
        "header": view_models.plan_header("year", selected, today.month, year_selected=selected),
        "year_view": view_models.year_view(rows),
        "year_selected": selected,
        "year_column_totals": column_totals,
        "year_grand_total": grand_total,
    }


def analytics_bundle(
    conn: sqlite3.Connection,
    user_id: int,
    today: date,
    picked: budget_service.PickerMonth,
    period_raw: str | None,
) -> tuple[AnalyticsBundle, dict[str, object]]:
    """Return the analytics bundle for the picked month and the keys derived from it."""
    period = analytics_service.normalize_period(period_raw)
    ref_today = analytics_service.reference_today(today, picked.year, picked.month)
    bundle = analytics_service.bundle(conn, user_id, today=ref_today, period=period)
    return bundle, {
        "bundle": bundle,
        "period": period,
        "spend_rows": view_models.spend_rows(
            bundle, analytics_service.twelve_month_avg_by_category(bundle)
        ),
        "spend_total_minor": analytics_service.spend_total_minor(bundle),
    }
