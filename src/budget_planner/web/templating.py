"""Jinja2 environment builder + shared filters/globals.

All Phase 3 routers extend the environment produced here; the goal is that
templates never need to import anything from Python other than filters
registered on `env`. See ADR-0021 (functional style) + T-030 plan.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import date, datetime
from pathlib import Path
from types import MappingProxyType

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.domain import category_colors
from budget_planner.domain.money import (
    ISO_4217_CURRENCIES,
    bps_to_percent,
    currency_decimals,
    format_major,
    format_money,
    format_whole,
    major_float,
    minor_to_major,
)
from budget_planner.web import view_models

_TEMPLATES_DIR = Path(__file__).parent / "templates"


def _money_filter(amount_minor: int | None, currency: str) -> str:
    if amount_minor is None:
        return ""
    return format_money(int(amount_minor), currency)


def _money_num_filter(
    amount_minor: int | None, currency: str, signed: bool = False, abs_value: bool = False
) -> str:
    """Grouped number in the currency's own decimals, no currency suffix (T-JPY).

    JPY/KRW render with 0 decimals, PLN/EUR with 2. ``signed`` forces a ``+``
    on positives; ``abs_value`` drops the sign (caller renders it).
    """
    if amount_minor is None:
        return ""
    value = minor_to_major(int(amount_minor), currency)
    if abs_value:
        value = abs(value)
    spec = f"{'+' if signed else ''},.{currency_decimals(currency)}f"
    return format(value, spec)


def _money_major_filter(amount_minor: int | None, currency: str) -> str:
    """Render minor-units as a bare major-unit decimal (no currency suffix).

    Preserves trailing fractional zeros for the currency's precision so edit
    forms round-trip values like ``15.50`` without the dot going missing.
    """
    if amount_minor is None:
        return ""
    return format_major(int(amount_minor), currency)


def _money_whole_filter(amount_minor: int | None, currency: str, grouped: bool = True) -> str:
    """Whole major units for dense tables (ADR-0006 amendment 2026-11-21)."""
    if amount_minor is None:
        return ""
    return format_whole(int(amount_minor), currency, grouped=grouped)


def _major_float_filter(amount_minor: int | None, currency: str) -> float:
    """Major-unit float for visual scales (heat weights), never for display text."""
    return major_float(int(amount_minor or 0), currency)


def _hero_fit_filter(amount_minor: int, currency: str) -> view_models.HeroFit:
    """``data-digits`` / ``data-marks`` / ``data-signs`` counts for a hero figure."""
    return view_models.hero_fit(int(amount_minor), currency)


def _bps_percent_filter(bps: int) -> str:
    """Basis points as a plain percent number (``150`` -> ``1.5``)."""
    return format(bps_to_percent(int(bps)).normalize(), "f")


def _date_fmt_filter(value: date | datetime | str | None, pattern: str = "%Y-%m-%d") -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            return value
        return parsed.strftime(pattern)
    return value.strftime(pattern)


# T-Q237 (G9): named date styles so templates never carry strftime patterns.
_DATE_STYLES: Mapping[str, str] = MappingProxyType(
    {
        "date_day_month": "%-d %b",
        "date_month_day": "%b %d",
        "date_month_year": "%b %Y",
        "date_day_month_year": "%d %b %Y",
        "date_year_month": "%Y-%m",
        "date_weekday_long": "%A · %d %B %Y",
    }
)


def _date_style_filter(pattern: str) -> Callable[[date | datetime | str | None], str]:
    def _styled(value: date | datetime | str | None) -> str:
        return _date_fmt_filter(value, pattern)

    return _styled


def _display_today_global(settings: Settings) -> Callable[[], str]:
    """Jinja global: today's date in `display_timezone` as ISO string (ADR-0030 §1, ADR-0140)."""

    def _display_today() -> str:
        return clock.today_local(settings).isoformat()

    return _display_today


def build_jinja_env(settings: Settings) -> Environment:
    """Return a fully-configured Jinja environment for the web layer."""
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "jinja2"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        enable_async=False,
    )
    env.filters["money"] = _money_filter
    env.filters["money_num"] = _money_num_filter
    env.filters["currency_decimals"] = currency_decimals
    env.filters["money_whole"] = _money_whole_filter
    env.filters["major_float"] = _major_float_filter
    env.filters["bps_percent"] = _bps_percent_filter
    env.filters["hero_fit"] = _hero_fit_filter
    env.filters["category_color"] = category_colors.category_color
    env.filters["bar_spans"] = view_models.bar_spans
    env.filters["bar_aria_label"] = view_models.bar_aria_label
    env.filters["direction_label"] = view_models.direction_label
    env.filters["year_cell_state"] = view_models.year_cell_state
    env.filters["money_major"] = _money_major_filter
    env.filters["date_fmt"] = _date_fmt_filter
    for name, pattern in _DATE_STYLES.items():
        env.filters[name] = _date_style_filter(pattern)
    env.globals["base_ccy"] = settings.base_currency
    # T-110 / ADR-0030 — shared primitives: default-date-today + ISO 4217 list.
    env.globals["today_local"] = _display_today_global(settings)
    env.globals["iso_4217_currencies"] = ISO_4217_CURRENCIES
    return env
