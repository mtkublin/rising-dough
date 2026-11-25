"""Ledger page view-models for the new shell (T-UR09, ADR-0107 section 3).

Pure: rows, day totals and filters in; the strings, ids and flags the handoff
markup prints out (``pages/ledger/actual*.html``). Money text comes from
``domain.money.format_figure`` (U+2212 and ``+`` owned there), the signed
effect of a row from ``services.ledger_totals.signed_effect``, category hues
from ``domain.category_colors``. Templates print these values and do no math.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import TYPE_CHECKING, Final
from urllib.parse import urlencode

from budget_planner.domain import category_colors
from budget_planner.domain.accounts import Account
from budget_planner.domain.categories import Category
from budget_planner.domain.enums import Direction
from budget_planner.domain.money import bps_to_percent, format_figure
from budget_planner.domain.recurring import AmountFormula, RecurringOverride
from budget_planner.services.ledger_totals import (
    DeltaDirection,
    OverrideDelta,
    PlannedStatus,
    PlannedStatusKind,
    PlannedTotals,
    RecurringTotals,
    signed_effect,
)
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
        "planned": "planned",
        "recurring": "recurring \N{MIDDLE DOT} per month",
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
    label: str = ""
    unit: str = ""
    note: str = ""
    wide: bool = False


def ledger_hero(spent_minor: int | None, currency: str) -> LedgerHero | None:
    """Hero of the Actual view; ``None`` when the figure is unknown."""
    if spent_minor is None:
        return None
    return LedgerHero(
        figure=format_figure(spent_minor, currency),
        fit=hero_fit(spent_minor, currency),
        currency=currency,
        unit=currency,
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


def _signed_text(amount: int, direction: Direction | None, currency: str) -> str:
    """Signed figure in the account's currency (ADR-0008); a transit shows ``⇄ amount``."""
    if direction is Direction.TRANSIT:
        return f"{_TRANSIT_GLYPH} {format_figure(amount, currency)}"
    if direction is None:
        return format_figure(amount, currency)
    return format_figure(signed_effect(amount, direction), currency, plus=True)


def _amount_text(row: TxnRow) -> str:
    return _signed_text(row.amount, row.category.direction if row.category else None, row.currency)


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
    return hue_rules(r.category for r in rows)


def hue_rules(categories: Iterable[Category | None]) -> str:
    """One style rule per distinct custom hue among ``categories`` (presets need none)."""
    rules = (
        category_colors.category_color(c.color).rule
        for c in categories
        if c is not None and c.color
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


# --- T-UR10a: the planned, recurring and recently-deleted views ---------------------------------

_RESTORE: Final = "restore"
_DELETE: Final = "delete"
_BULLET: Final = "\N{BLACK CIRCLE}"
_UP_TRIANGLE: Final = "\N{BLACK UP-POINTING TRIANGLE}"
_CHECK: Final = "\N{CHECK MARK}"
_REPEAT: Final = "\N{ANTICLOCKWISE OPEN CIRCLE ARROW}"
_MINUS: Final = "\N{MINUS SIGN}"
_FORMULA_SIGNS: Final[Mapping[str, str]] = MappingProxyType({"+": "+", "-": _MINUS})
_MONTH_NAMES: Final = (
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


def _days(count: int) -> str:
    return f"{count} day" if count == 1 else f"{count} days"


def _category(row: Mapping[str, object]) -> Category | None:
    value = row.get("category")
    return value if isinstance(value, Category) else None


def _account_name(row: Mapping[str, object]) -> str:
    value = row.get("account")
    return value.name if isinstance(value, Account) else ""


def _int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    return value if isinstance(value, int) else 0


def _date(row: Mapping[str, object], key: str) -> date:
    value = row.get(key)
    if not isinstance(value, date):
        raise TypeError(f"{key} is not a date")
    return value


def _str_of(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    return value if isinstance(value, str) else ""


def _hue(category: Category | None) -> str:
    return category_colors.category_color(category.color if category else None).name or ""


@dataclass(frozen=True, slots=True)
class DetailRow:
    """One line of the recurring detail panel: an override or a formula term."""

    label: str
    amount_text: str = ""
    delta_text: str = ""
    remove_url: str = ""
    remove_label: str = ""
    sign: str = ""
    sources: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class SchedRowView:
    """One planned or recurring row (``rows/planned-row`` and ``rows/recurring-row``)."""

    dom_id: str
    due_text: str
    title: str
    sub: str
    category_name: str
    category_hue: str
    amount_text: str
    currency: str
    menu_id: str
    menu_title: str
    menu_sub: str
    menu_items: tuple[MenuItem, ...]
    formula: bool = False
    status_text: str = ""
    status_kind: str = ""
    overrides_badge: str = ""
    promote_url: str = ""
    expand_id: str = ""
    new_override_url: str = ""
    override_rows: tuple[DetailRow, ...] = ()
    formula_rows: tuple[DetailRow, ...] = ()
    formula_next: str = ""


def _menu_item(
    label: str,
    *,
    get: str = "",
    post: str = "",
    swap: str = "",
    target: str = "",
    confirm: str = "",
    danger: bool = False,
    phone: bool = False,
) -> MenuItem:
    """A row-menu item with only the keys that are set (``fragments/menus/row-menu.html``)."""
    keys = {
        "hx_get": get,
        "hx_post": post,
        "hx_swap": swap,
        "hx_target": target,
        "hx_confirm": confirm,
    }
    flags = {"danger": danger, "phone": phone}
    return {
        "label": label,
        **{k: v for k, v in keys.items() if v},
        **{k: v for k, v in flags.items() if v},
    }


@dataclass(frozen=True, slots=True)
class CadenceGroup:
    """A cadence heading with its rule rows (MONTHLY, WEEKLY, ...)."""

    label: str
    rows: tuple[SchedRowView, ...]


def _status_cell(row: Mapping[str, object]) -> tuple[str, str]:
    """Status text and kind (promoted, overdue, today or later) of a planned row."""
    if row.get("is_promoted"):
        return f"{_CHECK} promoted", "promoted"
    status = row.get("status")
    if not isinstance(status, PlannedStatus):
        return "", ""
    if status.kind is PlannedStatusKind.OVERDUE:
        return f"{_UP_TRIANGLE} overdue {_days(status.days)}", "overdue"
    if status.kind is PlannedStatusKind.DUE_TODAY:
        return f"{_BULLET} due today", "today"
    return f"in {_days(status.days)}", "later"


def _planned_row_view(row: Mapping[str, object]) -> SchedRowView:
    category = _category(row)
    direction = category.direction if category else None
    currency = _str_of(row, "currency")
    amount = _signed_text(_int(row, "amount_minor"), direction, currency)
    title = _str_of(row, "description") or "\N{EM DASH}"
    sub = _account_name(row)
    due = _date(row, "operation_date")
    key = _str_of(row, "key")
    persisted = row.get("persisted_id")
    status_text, status_kind = _status_cell(row)
    promote = f"/planned/{persisted}/promote?dialog=1"
    promotable = isinstance(persisted, int) and not row.get("is_promoted")
    return SchedRowView(
        dom_id=f"planned-{key}",
        due_text=_short_date(due),
        title=title,
        sub=sub,
        category_name=category.name if category else "",
        category_hue=_hue(category),
        amount_text=amount,
        currency=currency,
        status_text=status_text,
        status_kind=status_kind,
        promote_url=promote if promotable else "",
        menu_id=f"menu-planned-{key}",
        menu_title=f"{title}{_SEP}{amount} {currency}",
        menu_sub=f"due {_short_date(due)}{_SEP}{sub}",
        menu_items=_planned_menu(persisted, key, promote if promotable else ""),
    )


def _planned_menu(persisted: object, key: str, promote_url: str) -> tuple[MenuItem, ...]:
    """Menu of a persisted planned item (promote below md while pending, edit, delete)."""
    if not isinstance(persisted, int):
        return ()
    base = f"/planned/{persisted}"
    items = [_menu_item("promote", get=promote_url, phone=True)] if promote_url else []
    items.append(_menu_item("edit", get=f"{base}/edit"))
    items.append(
        _menu_item(
            "delete",
            post=f"{base}/{_DELETE}",
            target=f"#planned-{key}",
            swap="outerHTML",
            confirm="Delete this planned entry?",
            danger=True,
        )
    )
    return tuple(items)


def planned_views(rows: Sequence[Mapping[str, object]]) -> tuple[SchedRowView, ...]:
    """The Planned table rows in list order."""
    return tuple(_planned_row_view(r) for r in rows)


def _override_label(day: date) -> str:
    return f"{_MONTH_NAMES[day.month - 1]} {day.year}"


def _delta_text(delta: OverrideDelta, currency: str) -> str:
    if delta.direction is DeltaDirection.UP:
        return format_figure(delta.magnitude_minor, currency, plus=True)
    if delta.direction is DeltaDirection.DOWN:
        return format_figure(-delta.magnitude_minor, currency)
    return format_figure(0, currency)


def _percent(bps: int) -> str:
    return format(bps_to_percent(bps).normalize(), "f")


def _override_rows(row: Mapping[str, object], rule_id: int, currency: str) -> tuple[DetailRow, ...]:
    deltas = row.get("override_deltas")
    overrides = row.get("overrides")
    if not isinstance(overrides, Sequence):
        return ()
    out: list[DetailRow] = []
    for ov in overrides:
        if not isinstance(ov, RecurringOverride):
            continue
        delta = deltas.get(ov.occurrence_date) if isinstance(deltas, Mapping) else None
        label = _override_label(ov.occurrence_date)
        out.append(
            DetailRow(
                label=label,
                amount_text=""
                if ov.amount_override is None
                else f"{format_figure(ov.amount_override, currency)} {currency}",
                delta_text=_delta_text(delta, currency) if isinstance(delta, OverrideDelta) else "",
                remove_url=f"/recurring/{rule_id}/overrides/new"
                f"?occurrence_date={ov.occurrence_date.isoformat()}&remove=1",
                remove_label=f"Remove override {label}",
            )
        )
    return tuple(out)


def _formula_rows(
    row: Mapping[str, object], names: Mapping[int, Category]
) -> tuple[DetailRow, ...]:
    formula = row.get("amount_formula")
    if not isinstance(formula, AmountFormula):
        return ()
    return tuple(
        DetailRow(
            label=f"{_percent(t.coefficient_bps)} %",
            sign=_FORMULA_SIGNS[t.sign],
            sources=tuple(
                (names[cid].name, _hue(names[cid])) for cid in t.source_category_ids if cid in names
            ),
        )
        for t in formula.terms
    )


def _recurring_row_view(row: Mapping[str, object], names: Mapping[int, Category]) -> SchedRowView:
    rule_id = _int(row, "id")
    category = _category(row)
    direction = category.direction if category else None
    currency = _str_of(row, "currency")
    effective = _int(row, "effective_amount_minor")
    amount = _signed_text(effective, direction, currency)
    title = _str_of(row, "default_description") or "\N{EM DASH}"
    sub = _account_name(row)
    due = _date(row, "next_due")
    overrides = _override_rows(row, rule_id, currency)
    formula = _formula_rows(row, names)
    count = len(overrides)
    return SchedRowView(
        dom_id=f"recurring-{rule_id}",
        due_text=_short_date(due),
        title=title,
        formula=bool(row.get("is_formula")),
        sub=sub,
        category_name=category.name if category else "",
        category_hue=_hue(category),
        amount_text=amount,
        currency=currency,
        overrides_badge=f"{_REPEAT} {count} override{'' if count == 1 else 's'}" if count else "",
        menu_id=f"menu-recurring-{rule_id}",
        menu_title=f"{title}{_SEP}{amount} {currency}",
        menu_sub=f"next {_short_date(due)}{_SEP}{sub}",
        menu_items=_recurring_menu(rule_id, due),
        expand_id=f"recurring-{rule_id}-expand" if overrides or formula else "",
        new_override_url=f"/recurring/{rule_id}/overrides/new",
        override_rows=overrides,
        formula_rows=formula,
        formula_next=f"{format_figure(effective, currency)} {currency}" if formula else "",
    )


def _recurring_menu(rule_id: int, due: date) -> tuple[MenuItem, ...]:
    """Menu of a rule: promote and override open dialogs; skip next and delete post and refetch."""
    base = f"/recurring/{rule_id}"
    return (
        _menu_item("promote", get=f"{base}/promote?dialog=1"),
        _menu_item("override", get=f"{base}/overrides/new"),
        _menu_item(
            "skip next", post=f"{base}/skip-next", swap="none", confirm=f"Skip {due.isoformat()}?"
        ),
        _menu_item("edit", get=f"{base}/edit"),
        _menu_item(
            "delete",
            post=f"{base}/deactivate",
            swap="none",
            confirm="Delete this recurring rule? Past promotions are kept.",
            danger=True,
        ),
    )


def recurring_groups(
    rows: Sequence[Mapping[str, object]], names: Mapping[int, Category]
) -> tuple[CadenceGroup, ...]:
    """Rule rows grouped by cadence in first-seen order (the list is sorted by next due)."""
    groups: dict[str, list[SchedRowView]] = {}
    for row in rows:
        cadence = row.get("cadence")
        label = str(getattr(cadence, "value", cadence)).upper()
        groups.setdefault(label, []).append(_recurring_row_view(row, names))
    return tuple(CadenceGroup(label, tuple(views)) for label, views in groups.items())


def schedule_hero(
    view: ViewKind,
    *,
    planned: PlannedTotals | None,
    recurring: RecurringTotals | None,
    currency: str,
) -> LedgerHero | None:
    """Hero of the Planned (net, pending) and Recurring (monthly out) views."""
    if view == "planned" and planned is not None:
        parts = [
            f"{planned.count} items",
            f"{planned.overdue_count} overdue",
            f"{planned.due_today_count} due today",
        ]
        return LedgerHero(
            figure=format_figure(planned.net_minor, currency),
            fit=hero_fit(planned.net_minor, currency),
            currency=currency,
            label="planned",
            unit=f"{currency} net",
            note=_SEP.join(parts),
        )
    if view == "recurring" and recurring is not None:
        out = -recurring.monthly_out_minor
        parts = [
            f"in {format_figure(recurring.monthly_in_minor, currency, plus=True)}",
            f"{recurring.rule_count} rules",
        ]
        if recurring.next_due is not None:
            parts.append(f"next due {_short_date(recurring.next_due).lower()}")
        return LedgerHero(
            figure=format_figure(out, currency),
            fit=hero_fit(out, currency),
            currency=currency,
            label="recurring \N{MIDDLE DOT} per month",
            unit=f"{currency} out",
            note=_SEP.join(parts),
            wide=True,
        )
    return None


@dataclass(frozen=True, slots=True)
class DeletedRowView:
    """One recently-deleted row (transaction, planned item or category)."""

    dom_id: str
    deleted_at: str
    due_text: str
    title: str
    category_name: str
    category_hue: str
    direction_text: str
    amount_text: str
    restore_url: str


_DIRECTION_ARROWS: Final[Mapping[str, str]] = MappingProxyType(
    {"income": "\N{UPWARDS ARROW}", "expense": "\N{DOWNWARDS ARROW}", "transit": _TRANSIT_GLYPH}
)


def _restore_url(collection: str, entity_id: int) -> str:
    return f"/{collection}/{entity_id}/{_RESTORE}"


def deleted_money_row(
    kind: str,
    entity_id: int,
    *,
    deleted_at: str,
    day: date,
    description: str | None,
    amount: int,
    category: Category | None,
    account: Account | None,
) -> DeletedRowView:
    """A deleted transaction (``kind`` txn) or planned item (planned): signed figure and restore."""
    currency = account.currency if account else ""
    direction = category.direction if category else None
    return DeletedRowView(
        dom_id=f"deleted-{kind}-{entity_id}",
        deleted_at=deleted_at,
        due_text=_short_date(day),
        title=description or "\N{EM DASH}",
        category_name=category.name if category else "",
        category_hue=_hue(category),
        direction_text="",
        amount_text=f"{_signed_text(amount, direction, currency)} {currency}".strip(),
        restore_url=_restore_url("transactions" if kind == "txn" else "planned", entity_id),
    )


def deleted_category_row(category: Category, *, deleted_at: str) -> DeletedRowView:
    """A deleted (archived) category: name chip, direction and restore."""
    value = category.direction.value
    return DeletedRowView(
        dom_id=f"deleted-category-{category.id}",
        deleted_at=deleted_at,
        due_text="",
        title="",
        category_name=category.name,
        category_hue=_hue(category),
        direction_text=f"{_DIRECTION_ARROWS.get(value, '')} {_DIRECTION_LABELS.get(value, value)}",
        amount_text="",
        restore_url=_restore_url("categories", category.id),
    )
