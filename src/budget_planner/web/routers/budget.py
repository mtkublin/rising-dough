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
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from budget_planner.config import Settings
from budget_planner.domain.budgets import (
    NewBudgetDefault,
    NewBudgetOneOffOverride,
    NewBudgetRecurringOverride,
)
from budget_planner.domain.enums import Direction
from budget_planner.domain.money import to_minor_units
from budget_planner.repositories import (
    budgets as budgets_repo,
    categories as categories_repo,
)
from budget_planner.services import budget as budget_service, preferences as preferences_svc
from budget_planner.services.preferences import InvalidAnchorCategoryError
from budget_planner.web.deps import get_db, get_settings_dep
from budget_planner.web.htmx import trigger
from budget_planner.web.rendering import render

router = APIRouter(prefix="/budget", tags=["budget"])

_MONTHS_IN_YEAR = 12


@dataclass(frozen=True, slots=True)
class RulesRow:
    """One row of the Rules editor table (ADR-0031 §2 — category + default)."""

    category_id: int
    category_name: str
    category_direction: Direction
    category_color: str | None
    default_minor: int | None


_MONTH_LABELS: tuple[str, ...] = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def _year_month(request: Request, conn: sqlite3.Connection) -> tuple[int, int]:
    """Default landing month = fiscal cycle (ADR-0064); overridable via query."""
    q = request.query_params
    today = date.today()  # noqa: DTZ011
    fiscal_year, fiscal_month = budget_service.fiscal_month_for(conn, today)
    year = int(q.get("year", fiscal_year))
    month = int(q.get("month", fiscal_month))
    return year, month


def _rules_rows(conn: sqlite3.Connection) -> tuple[RulesRow, ...]:
    """Per-expense-category rows for the Rules editor (ADR-0031 §2).

    Each row carries only the default amount (nullable); recurring + one-off
    overrides are authored on demand via the per-row Override… slide-over.
    """
    cats = [
        c
        for c in categories_repo.list_all(conn)
        if not c.is_system and c.direction is Direction.EXPENSE
    ]
    defaults = {d.category_id: d.amount for d in budgets_repo.list_defaults(conn)}
    rows = [
        RulesRow(
            category_id=cat.id,
            category_name=cat.name,
            category_direction=cat.direction,
            category_color=cat.color,
            default_minor=defaults.get(cat.id),
        )
        for cat in cats
    ]
    rows.sort(key=lambda r: r.category_name.casefold())
    return tuple(rows)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _render_index(
    request: Request,
    conn: sqlite3.Connection,
    settings: Settings,
) -> HTMLResponse:
    year, month = _year_month(request, conn)
    today = datetime.now(ZoneInfo(settings.display_timezone)).date()
    summary = budget_service.month_summary(conn, year, month, today=today)
    rules = _rules_rows(conn)
    yearly = budget_service.yearly_grid(conn, year)
    return render(
        request,
        "budget/index.html",
        year=year,
        month=month,
        summary=summary,
        rules=rules,
        yearly=yearly,
        month_labels=_MONTH_LABELS,
        base_ccy=settings.base_currency,
    )


@router.get("/yearly", response_class=HTMLResponse)
def yearly_fragment(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> HTMLResponse:
    """HTMX fragment for the Yearly grid (ADR-0031 §3).

    Returns just the ``#budget-yearly`` section so year switching does not
    force a full-page reload.
    """
    q = request.query_params
    today = datetime.now(ZoneInfo(settings.display_timezone)).date()
    year = int(q.get("year", today.year))
    yearly = budget_service.yearly_grid(conn, year)
    return render(
        request,
        "budget/_yearly.html",
        year=year,
        yearly=yearly,
        month_labels=_MONTH_LABELS,
        base_ccy=settings.base_currency,
    )


@router.get("/rules/{category_id}/overrides/new", response_class=HTMLResponse)
def new_override_form(
    category_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> HTMLResponse:
    """Slide-over form for creating a recurring / one-off override (ADR-0031 §2).

    Optional ``month`` / ``year`` query params prefill the fields when the
    form is opened from the Year heatmap (ADR-0051 §5.3).
    """
    cat = categories_repo.find_by_id(conn, category_id)
    tz_year = datetime.now(ZoneInfo(settings.display_timezone)).year
    q = request.query_params
    try:
        preset_month = int(q["month"]) if "month" in q else None
    except ValueError:
        preset_month = None
    if preset_month is not None and (preset_month < 1 or preset_month > _MONTHS_IN_YEAR):
        preset_month = None
    try:
        preset_year = int(q["year"]) if "year" in q else None
    except ValueError:
        preset_year = None
    if cat is None:
        return render(
            request,
            "partials/budget/_override_form.html",
            category=None,
            errors={"category": "not found"},
            today_year=tz_year,
            preset_month=preset_month,
            preset_year=preset_year,
            status_code=404,
        )
    default_row = budgets_repo.get_default(conn, category_id)
    inline = q.get("inline") == "1"
    if inline:
        return render(
            request,
            "partials/budget/_override_form.html",
            category=cat,
            errors={},
            today_year=tz_year,
            preset_month=preset_month,
            preset_year=preset_year,
            default_amount_minor=default_row.amount if default_row else None,
        )
    return render(
        request,
        "partials/_slideover.html",
        slide_over_title=f"Override · {cat.name}",
        form_include="partials/budget/_override_form.html",
        category=cat,
        errors={},
        today_year=tz_year,
        preset_month=preset_month,
        preset_year=preset_year,
        default_amount_minor=default_row.amount if default_row else None,
    )


@router.post("/rules/{category_id}/overrides")
def create_override(  # noqa: PLR0911, PLR0917
    category_id: int,
    tier: str = Form(...),
    month: str = Form(""),
    year: str = Form(""),
    amount: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> Response:
    """Tier-dispatcher for the Override slide-over (ADR-0031 §2)."""
    cat = categories_repo.find_by_id(conn, category_id)
    if cat is None:
        return Response(status_code=404, content="not found")
    if tier not in {"recurring", "one-off", "default"}:
        return Response(status_code=422, content="invalid tier")
    dec = _parse_decimal(amount) if amount.strip() else Decimal(0)
    if dec is None or dec < 0:
        return Response(status_code=422, content="invalid amount")
    minor = to_minor_units(dec, settings.base_currency)
    if tier == "default":
        budgets_repo.set_default(
            conn,
            NewBudgetDefault(category_id=category_id, amount=minor),
        )
        resp = Response(content="ok", media_type="text/html")
        trigger(resp, "budget-stale")
        return resp
    try:
        parsed_month = int(month)
    except ValueError:
        return Response(status_code=422, content="invalid month")
    if parsed_month < 1 or parsed_month > _MONTHS_IN_YEAR:
        return Response(status_code=422, content="invalid month")
    if tier == "recurring":
        budgets_repo.set_recurring(
            conn,
            NewBudgetRecurringOverride(category_id=category_id, month=parsed_month, amount=minor),
        )
    else:
        try:
            parsed_year = int(year)
        except ValueError:
            return Response(status_code=422, content="invalid year")
        budgets_repo.set_one_off(
            conn,
            NewBudgetOneOffOverride(
                category_id=category_id,
                year=parsed_year,
                month=parsed_month,
                amount=minor,
            ),
        )
    resp = Response(content="ok", media_type="text/html")
    trigger(resp, "budget-stale")
    return resp


@router.get("", response_class=HTMLResponse)
def index(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> HTMLResponse:
    return _render_index(request, conn, settings)


@router.get("/manage")
def manage() -> RedirectResponse:
    """Legacy page URL (T-070).

    Redirects to the ``/budget`` Rules section anchor. Kept at ``302`` for
    one release per ADR-0023; a follow-up task flips to ``301``.
    """
    return RedirectResponse(url="/budget#budget-rules", status_code=302)


def _parse_decimal(value: str) -> Decimal | None:
    try:
        dec = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not dec.is_finite():
        return None
    return dec


@router.post("/defaults/{category_id}")
def set_default(
    category_id: int,
    amount: str = Form(...),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> Response:
    cat = categories_repo.find_by_id(conn, category_id)
    if cat is None:
        return Response(status_code=404, content="not found")
    dec = _parse_decimal(amount)
    if dec is None or dec < 0:
        return Response(status_code=422, content="invalid amount")
    minor = to_minor_units(dec, settings.base_currency)
    budgets_repo.set_default(conn, NewBudgetDefault(category_id=category_id, amount=minor))
    resp = Response(content="ok", media_type="text/html")
    trigger(resp, "budget-stale")
    return resp


@router.post("/recurring/{category_id}/{month}")
def set_recurring(
    category_id: int,
    month: int,
    amount: str = Form(...),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> Response:
    cat = categories_repo.find_by_id(conn, category_id)
    if cat is None:
        return Response(status_code=404, content="not found")
    if month < 1 or month > _MONTHS_IN_YEAR:
        return Response(status_code=422, content="invalid month")
    dec = _parse_decimal(amount)
    if dec is None or dec < 0:
        return Response(status_code=422, content="invalid amount")
    minor = to_minor_units(dec, settings.base_currency)
    budgets_repo.set_recurring(
        conn,
        NewBudgetRecurringOverride(category_id=category_id, month=month, amount=minor),
    )
    resp = Response(content="ok", media_type="text/html")
    trigger(resp, "budget-stale")
    return resp


@router.post("/preferences/income-anchor")
def set_income_anchor(
    category_id: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
) -> Response:
    """Set or clear the income anchor preference (ADR-0025, F4.7).

    An empty ``category_id`` clears the preference. A numeric value must
    point at a live INCOME-direction category.
    """
    raw = category_id.strip()
    if raw == "":
        preferences_svc.set_income_anchor_category_id(conn, 1, None)
    else:
        try:
            parsed = int(raw)
        except ValueError:
            return Response(status_code=422, content="invalid category_id")
        try:
            preferences_svc.set_income_anchor_category_id(conn, 1, parsed)
        except InvalidAnchorCategoryError as err:
            return Response(status_code=422, content=str(err))
    resp = Response(content="ok", media_type="text/html")
    trigger(resp, "budget-stale")
    return resp


@router.post("/one-off/{category_id}/{year}/{month}")
def set_one_off(  # noqa: PLR0917
    category_id: int,
    year: int,
    month: int,
    amount: str = Form(...),
    conn: sqlite3.Connection = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> Response:
    cat = categories_repo.find_by_id(conn, category_id)
    if cat is None:
        return Response(status_code=404, content="not found")
    if month < 1 or month > _MONTHS_IN_YEAR:
        return Response(status_code=422, content="invalid month")
    dec = _parse_decimal(amount)
    if dec is None or dec < 0:
        return Response(status_code=422, content="invalid amount")
    minor = to_minor_units(dec, settings.base_currency)
    budgets_repo.set_one_off(
        conn,
        NewBudgetOneOffOverride(category_id=category_id, year=year, month=month, amount=minor),
    )
    resp = Response(content="ok", media_type="text/html")
    trigger(resp, "budget-stale")
    return resp
