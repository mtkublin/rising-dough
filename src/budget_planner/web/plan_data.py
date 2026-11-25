"""Template-context assembly for the Plan hub (ADR-0051 section 5, ADR-0138).

No business logic: services compute, this module only names the template keys.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import get_args

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.services import (
    analytics as analytics_service,
    budget as budget_service,
    budget_overrides as budget_overrides_service,
    categories as categories_service,
    forecast as forecast_service,
    fortune as fortune_service,
    fx as fx_service,
)
from budget_planner.services.forecast import MonthlyProjectionPoint
from budget_planner.web import plan_views, plan_year_view, view_models
from budget_planner.web.params import query_choice

BUDGET_TAB_URL = "/plan?tab=budget"
"""Base of the budget tab's period links (``&year=&month=`` follow)."""
FORECAST_TAB_URL = "/plan?tab=forecast&horizon="
"""Base of the forecast tab's horizon links (the months follow)."""


def forecast_summary(
    conn: sqlite3.Connection,
    user_id: int,
    settings: Settings,
    today: date,
    projection: tuple[MonthlyProjectionPoint, ...],
) -> forecast_service.ProjectionSummary | None:
    """Summary strip whose NOW is today's net worth, as on Accounts (ADR-0151 section 2)."""
    net_worth = fortune_service.compute_fortune(
        conn, user_id, fx_service.converter_for(conn, settings, today)
    ).net_base
    return forecast_service.projection_summary(projection, now_value=net_worth)


def forecast_page_for(
    conn: sqlite3.Connection,
    user_id: int,
    settings: Settings,
    today: date,
    *,
    horizon: int,
    choices: tuple[int, ...],
) -> plan_views.ForecastPageView:
    """Hero, chart and table values of Plan · forecast for ``horizon`` months."""
    projection = forecast_service.monthly_projection(
        conn, user_id, settings, today, horizon=horizon
    )
    return plan_views.forecast_page(
        projection,
        forecast_summary(conn, user_id, settings, today, projection),
        horizon=horizon,
        choices=choices,
        currency=settings.base_currency,
        base_url=FORECAST_TAB_URL,
    )


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


def budget_view_for(
    conn: sqlite3.Connection,
    user_id: int,
    picked: budget_service.PickerMonth,
    today: date,
    settings: Settings,
) -> view_models.BudgetView:
    """Return the Plan · Budget view model for the picked month."""
    summary = budget_service.month_summary_for_picker(
        conn,
        user_id,
        picked,
        today,
        base_currency=settings.base_currency,
        display_timezone=settings.display_timezone,
    )
    return view_models.budget_view(summary, today, settings.base_currency)


def budget_period_for(
    picked: budget_service.PickerMonth, budget: view_models.BudgetView
) -> view_models.BudgetPeriod:
    """Return the Plan · Budget period nav (arrows and picker) for the picked month."""
    return view_models.budget_period(picked, budget.summary, BUDGET_TAB_URL)


def year_page_for(
    conn: sqlite3.Connection,
    user_id: int,
    today: date,
    year_raw: str | None,
    *,
    settings: Settings,
) -> plan_year_view.YearPage:
    """Plan · year values for the requested (or fiscal) year."""
    selected = budget_service.resolve_picker_month(conn, user_id, today, year_raw=year_raw).year
    rows = budget_service.yearly_grid(
        conn, user_id, selected, display_timezone=settings.display_timezone
    )
    return plan_year_view.year_page(
        rows, selected, current=(today.year, today.month), currency=settings.base_currency
    )


def override_state(
    conn: sqlite3.Connection, user_id: int, category_id: int, year: int, month: int
) -> plan_year_view.OverrideState:
    """The stored one-off, recurring and default amounts of a category and month."""
    one_off = budget_overrides_service.get_one_off(conn, user_id, category_id, year, month)
    recurring = budget_overrides_service.get_recurring(conn, user_id, category_id, month)
    default = budget_overrides_service.get_default(conn, user_id, category_id)
    return plan_year_view.OverrideState(
        one_off=None if one_off is None else one_off.amount,
        recurring=None if recurring is None else recurring.amount,
        default=None if default is None else default.amount,
    )


def override_dialog_for(
    conn: sqlite3.Connection,
    user_id: int,
    target: plan_year_view.OverrideTarget,
    *,
    tier: str,
    currency: str,
    amount_text: str | None = None,
    error: str | None = None,
) -> plan_year_view.OverrideDialog:
    """The override dialog of a category and month on scope ``tier``."""
    state = override_state(conn, user_id, target.category_id, target.year, target.month)
    return plan_year_view.override_dialog(
        target, tier=tier, state=state, currency=currency, amount_text=amount_text, error=error
    )


def remove_confirm_for(
    conn: sqlite3.Connection,
    user_id: int,
    target: plan_year_view.OverrideTarget,
    *,
    tier: str,
    currency: str,
) -> plan_year_view.RemoveConfirm:
    """The remove confirm for the ``tier`` override of a category and month."""
    state = override_state(conn, user_id, target.category_id, target.year, target.month)
    return plan_year_view.remove_confirm(target, tier=tier, state=state, currency=currency)


def analytics_page_for(
    conn: sqlite3.Connection,
    user_id: int,
    picked: budget_service.PickerMonth,
    period_raw: str | None,
    *,
    settings: Settings,
) -> plan_views.AnalyticsPageView:
    """Plan · analytics values for the picked month and the requested range."""
    today = clock.today_local(settings)
    period = analytics_service.normalize_period(
        query_choice("period", period_raw, get_args(analytics_service.Period))
    )
    bundle = analytics_service.bundle(
        conn,
        user_id,
        fx_service.converter_for(conn, settings, today),
        today=analytics_service.reference_today(today, picked.year, picked.month),
        period=period,
    )
    colors = {
        c.id: c.color for c in categories_service.list_all(conn, user_id, include_deleted=True)
    }
    return plan_views.analytics_page(bundle, picked, colors, settings.base_currency)
