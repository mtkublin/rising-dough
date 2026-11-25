"""Ledger page view-models for the new shell (T-UR09, ADR-0107 section 3).

Pure: rows, day totals and filters in; the strings, ids and flags the handoff
markup prints out (``pages/ledger/actual*.html``). Money text comes from
``domain.money.format_figure`` (U+2212 and ``+`` owned there), the signed
effect of a row from ``services.ledger_totals.signed_effect``, category hues
from ``domain.category_colors``. Templates print these values and do no math.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import TYPE_CHECKING, Final
from urllib.parse import urlencode

from budget_planner.domain import category_colors
from budget_planner.domain.accounts import Account
from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.domain.money import format_figure
from budget_planner.services.ledger_totals import signed_effect
from budget_planner.web.ledger_export import filter_query
from budget_planner.web.ledger_types import LedgerFilters, ViewKind, view_kinds
from budget_planner.web.view_models import MONTH_SHORT, HeroFit, hero_fit

if TYPE_CHECKING:
    from budget_planner.web.ledger_data import FilterSummary, TxnRow

_WEEKDAYS: Final = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
_TRANSIT_GLYPH: Final = "\N{LEFT RIGHT ARROW}"
_ARROW: Final = "\N{RIGHTWARDS ARROW}"
_EN_DASH: Final = "\N{EN DASH}"
_QUOTES: Final = ("\N{LEFT DOUBLE QUOTATION MARK}", "\N{RIGHT DOUBLE QUOTATION MARK}")
_SEP: Final = " \N{MIDDLE DOT} "
_DIRECTION_LABELS: Final[Mapping[str, str]] = MappingProxyType(
    {"expense": "expense", "income": "income", "transit": "transfer"}
)


VIEW_TITLES: Final[Mapping[ViewKind, str]] = MappingProxyType(
    {
        "actual": "spent this period",
        "planned": "Planned one-offs",
        "recurring": "Standing commitments",
    }
)


@dataclass(frozen=True, slots=True)
class LedgerTab:
    """One view tab (``actual 616``)."""

    label: str
    href: str
    current: bool


def ledger_tabs(view: ViewKind, counts: Mapping[str, int]) -> tuple[LedgerTab, ...]:
    """The three view tabs with their counts; ``actual`` links to the bare ``/ledger``."""
    return tuple(
        LedgerTab(
            label=f"{kind} {counts[kind]}" if kind in counts else kind,
            href="/ledger" if kind == "actual" else f"/ledger?view={kind}",
            current=kind == view,
        )
        for kind in view_kinds()
    )


@dataclass(frozen=True, slots=True)
class LedgerHero:
    """The "spent this period" figure (omitted when a needed FX rate is not cached)."""

    figure: str
    fit: HeroFit
    currency: str


def ledger_hero(spent_minor: int | None, currency: str) -> LedgerHero | None:
    """Hero of the Actual view; ``None`` when the figure is unknown."""
    if spent_minor is None:
        return None
    return LedgerHero(
        figure=format_figure(spent_minor, currency),
        fit=hero_fit(spent_minor, currency),
        currency=currency,
    )


@dataclass(frozen=True, slots=True)
class FilterOption:
    """One ``<option>`` of a filter select."""

    value: str
    label: str
    selected: bool


@dataclass(frozen=True, slots=True)
class FilterBar:
    """Values of ``fragments/ledger/filter-bar.html`` (query names stay the contract's)."""

    date_from: str
    date_to: str
    search: str
    categories: tuple[FilterOption, ...]
    accounts: tuple[FilterOption, ...]
    directions: tuple[FilterOption, ...]
    expanded: bool


def filter_bar(
    filters: LedgerFilters,
    categories: Sequence[Category],
    accounts: Sequence[Account],
) -> FilterBar:
    """Select options with the active filter marked; the bar opens when a filter is active."""
    return FilterBar(
        date_from=filters.date_from.isoformat() if filters.date_from else "",
        date_to=filters.date_to.isoformat() if filters.date_to else "",
        search=filters.search or "",
        categories=tuple(
            FilterOption(str(c.id), c.name, c.id in filters.category_ids) for c in categories
        ),
        accounts=tuple(
            FilterOption(str(a.id), a.name, a.id in filters.account_ids) for a in accounts
        ),
        directions=tuple(
            FilterOption(value, label, filters.direction == value)
            for value, label in _DIRECTION_LABELS.items()
        ),
        expanded=bool(
            filters.date_from or filters.date_to or filters.category_ids or filters.account_ids
        ),
    )


def _short_date(day: date) -> str:
    return f"{day.day:02d} {MONTH_SHORT[day.month - 1].upper()}"


def _numeric_date(day: date) -> str:
    return f"{day.day:02d}/{day.month:02d}/{day.year}"


def no_matches_text(summary: FilterSummary) -> str:
    """The active filters by name for the no-matches state (names, direction, dates, search)."""
    parts: list[str] = [*summary.category_names, *summary.account_names]
    if summary.direction:
        parts.append(_DIRECTION_LABELS.get(summary.direction, summary.direction))
    if summary.date_from and summary.date_to:
        span = f"{_numeric_date(summary.date_from)} {_EN_DASH} {_numeric_date(summary.date_to)}"
        parts.append(span)
    elif summary.date_from:
        parts.append(f"from {_numeric_date(summary.date_from)}")
    elif summary.date_to:
        parts.append(f"until {_numeric_date(summary.date_to)}")
    if summary.search:
        parts.append(f"{_QUOTES[0]}{summary.search}{_QUOTES[1]}")
    return _SEP.join(parts)


MenuItem = Mapping[str, str | bool]
"""One row-menu item: the keys ``fragments/menus/row-menu.html`` reads (unset keys omitted)."""


@dataclass(frozen=True, slots=True)
class TxnRowView:
    """One transaction row of the Actual table."""

    id: int
    title: str
    sub: str
    category_name: str
    category_hue: str
    amount_text: str
    currency: str
    select_label: str
    menu_id: str
    menu_title: str
    menu_sub: str
    menu_items: tuple[MenuItem, ...]


@dataclass(frozen=True, slots=True)
class TxnDayView:
    """A day group: the heading with its net, then the day's rows."""

    label: str
    net_text: str
    rows: tuple[TxnRowView, ...]


def _amount_text(row: TxnRow) -> str:
    """Signed figure in the account's currency (ADR-0008); a transit shows ``⇄ amount``."""
    direction = row.category.direction if row.category else None
    if direction is Direction.TRANSIT:
        return f"{_TRANSIT_GLYPH} {format_figure(row.amount, row.currency)}"
    if direction is None:
        return format_figure(row.amount, row.currency)
    return format_figure(signed_effect(row.amount, direction), row.currency, plus=True)


def _txn_row_view(row: TxnRow) -> TxnRowView:
    title = row.description or "\N{EM DASH}"
    account = row.account.name if row.account else ""
    sub = f"{account} {_ARROW} {row.dest_account.name}" if row.dest_account else account
    amount = _amount_text(row)
    category = row.category.name if row.category else ""
    colour = category_colors.category_color(row.category.color if row.category else None)
    base = f"/transactions/{row.id}"
    return TxnRowView(
        id=row.id,
        title=title,
        sub=sub,
        category_name=category,
        category_hue=colour.name or "",
        amount_text=amount,
        currency=row.currency,
        select_label=f"Select {title}, {amount} {row.currency}",
        menu_id=f"menu-txn-{row.id}",
        menu_title=f"{title}{_SEP}{amount} {row.currency}",
        menu_sub=f"{_short_date(row.operation_date)}{_SEP}{sub}",
        menu_items=(
            {"label": "edit", "hx_get": f"{base}/edit"},
            {
                "label": "delete",
                "hx_post": f"{base}/delete",
                "hx_target": f"#txn-{row.id}",
                "hx_swap": "outerHTML",
                "hx_confirm": "Delete this transaction?",
                "danger": True,
            },
        ),
    )


def actual_days(
    rows: Sequence[TxnRow], day_nets: Mapping[str, int | None], base_currency: str
) -> tuple[TxnDayView, ...]:
    """Group rows (already newest first) by operation date; the net is in the base currency."""
    days: list[tuple[date, list[TxnRowView]]] = []
    for row in rows:
        if not days or days[-1][0] != row.operation_date:
            days.append((row.operation_date, []))
        days[-1][1].append(_txn_row_view(row))
    out: list[TxnDayView] = []
    for day, views in days:
        net = day_nets.get(day.isoformat())
        out.append(
            TxnDayView(
                label=f"{_WEEKDAYS[day.weekday()]} {_short_date(day)}",
                net_text=""
                if net is None
                else f"NET {format_figure(net, base_currency, plus=True)}",
                rows=tuple(views),
            )
        )
    return tuple(out)


def category_rules(rows: Sequence[TxnRow]) -> str:
    """Style rules for hues outside the presets among the shown rows (one per distinct hue)."""
    rules = (
        category_colors.category_color(r.category.color).rule
        for r in rows
        if r.category is not None and r.category.color
    )
    return "".join(dict.fromkeys(rule for rule in rules if rule))


def ledger_url(view: ViewKind, filters: LedgerFilters) -> str:
    """The canonical page URL of a view under the live filters (what a reload must reopen)."""
    return "/ledger?" + urlencode([("view", view), *filter_query(filters)])


@dataclass(frozen=True, slots=True)
class PageLinks:
    """Pagination of the Actual view (plain links; page 1 has no newer link)."""

    page: int
    newer_url: str | None
    older_url: str | None


def page_links(filters: LedgerFilters, *, has_next: bool) -> PageLinks:
    """Links to the neighbouring pages, carrying the live filters."""
    base = [("view", "actual"), *filter_query(filters)]
    if filters.page_size != LedgerFilters().page_size:
        base.append(("page_size", str(filters.page_size)))

    def url(page: int) -> str:
        return "/ledger?" + urlencode([*base, ("page", str(page))])

    return PageLinks(
        page=filters.page,
        newer_url=url(filters.page - 1) if filters.page > 1 else None,
        older_url=url(filters.page + 1) if has_next else None,
    )
