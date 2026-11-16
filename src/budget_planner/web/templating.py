"""Jinja2 environment builder + shared filters/globals.

All Phase 3 routers extend the environment produced here; the goal is that
templates never need to import anything from Python other than filters
registered on `env`. See ADR-0021 (functional style) + T-030 plan.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from markupsafe import Markup, escape

from budget_planner.config import Settings
from budget_planner.domain.enums import Direction
from budget_planner.domain.money import (
    ISO_4217_CURRENCIES,
    currency_decimals,
    format_money,
    from_minor_units,
)

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
    value = from_minor_units(int(amount_minor), currency)
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
    decimals = currency_decimals(currency)
    value = from_minor_units(int(amount_minor), currency)
    return f"{value:.{decimals}f}"


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


def _dt_local_factory(tz_name: str) -> Any:
    tz = ZoneInfo(tz_name)

    def _dt_local(value: datetime | str | None, pattern: str = "%Y-%m-%d %H:%M") -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                return value
        else:
            parsed = value
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(tz).strftime(pattern)

    return _dt_local


_DIRECTION_COLORS: dict[str, str] = {
    Direction.INCOME.value: "pill-income",
    Direction.EXPENSE.value: "pill-expense",
    Direction.TRANSIT.value: "pill-transit",
    Direction.ADJUSTMENT.value: "pill-adjust",
}

# ADR-0048: CSS color used when a category has no override. Keeps the direction
# palette in a single lookup; the actual oklch values live in app.css under the
# matching custom properties.
_DIRECTION_CSS_VARS: dict[str, str] = {
    Direction.INCOME.value: "var(--income)",
    Direction.EXPENSE.value: "var(--expense)",
    Direction.TRANSIT.value: "var(--transit)",
    Direction.ADJUSTMENT.value: "var(--adjust)",
}


def _direction_badge(direction: Direction | str | None) -> Markup:
    if direction is None:
        return Markup("")
    value = direction.value if isinstance(direction, Direction) else str(direction)
    css = _DIRECTION_COLORS.get(value, "pill-adjust")
    label = value.capitalize()
    # Values come from the Direction StrEnum or a bounded string set; label is
    # just capitalised. Safe to mark as Markup — content is derived not user.
    return Markup(  # noqa: S704
        f'<span class="pill {css}" aria-label="{label}">{label}</span>'
    )


def _resolve_category_color(direction: Direction | str | None, color: str | None) -> str:
    """Return the CSS color for a category: hex override else direction var.

    ADR-0048 — ``color`` is a 6-digit lowercase hex (validated at the service
    layer); falsy means "inherit direction". Unknown direction falls back to
    the adjustment hue.
    """
    if color:
        return color
    if direction is None:
        return _DIRECTION_CSS_VARS[Direction.ADJUSTMENT.value]
    value = direction.value if isinstance(direction, Direction) else str(direction)
    return _DIRECTION_CSS_VARS.get(value, _DIRECTION_CSS_VARS[Direction.ADJUSTMENT.value])


def _category_label_parts(
    name: str | None,
    direction: Direction | str | None,
    color: str | None,
) -> Markup:
    """Render a category pill (background wash + foreground hue) from scalars.

    ADR-0048 — matches the ``.pill`` shape used by ``direction_badge`` so the
    category identity reads as a chip, not plain text. Background is a 16%
    oklab wash of the resolved hue; foreground is the hue itself. The hue is
    the override hex when set, otherwise ``var(--income|--expense|…)``.
    """
    if not name:
        return Markup("")
    css_color = _resolve_category_color(direction, color)
    safe_name = escape(name)
    style = f"background: color-mix(in oklab, {css_color} 16%, transparent); color: {css_color}"
    return Markup(  # noqa: S704
        f'<span class="pill cat-pill" style="{style}">{safe_name}</span>'
    )


def _category_label(category: Any) -> Markup:
    """Render a coloured category name span from a ``Category``-shaped object.

    Accepts anything with ``name`` / ``direction`` / ``color`` attributes.
    Returns empty Markup for ``None`` so templates can call it without a
    surrounding guard.
    """
    if category is None:
        return Markup("")
    return _category_label_parts(
        getattr(category, "name", None),
        getattr(category, "direction", None),
        getattr(category, "color", None),
    )


def _csrf_token() -> str:
    # v1 single-user, no auth (ADR-0005). Keep the attr shape stable.
    return ""


def _today_local_factory(tz_name: str) -> Any:
    """Return today's date in `display_timezone` as ISO string (ADR-0030 §1)."""
    tz = ZoneInfo(tz_name)

    def _today_local() -> str:
        return datetime.now(tz).date().isoformat()

    return _today_local


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
    env.filters["money_major"] = _money_major_filter
    env.filters["date_fmt"] = _date_fmt_filter
    env.filters["dt_local"] = _dt_local_factory(settings.display_timezone)
    env.filters["direction_badge"] = _direction_badge
    env.globals["direction_badge"] = _direction_badge
    # ADR-0048 — colour the category name across every surface it appears.
    env.globals["category_label"] = _category_label
    env.globals["category_label_parts"] = _category_label_parts
    env.globals["base_ccy"] = settings.base_currency
    env.globals["csrf_token"] = _csrf_token
    env.globals["Direction"] = Direction
    # T-110 / ADR-0030 — shared primitives: default-date-today + ISO 4217 list.
    env.globals["today_local"] = _today_local_factory(settings.display_timezone)
    env.globals["iso_4217_currencies"] = ISO_4217_CURRENCIES
    return env
