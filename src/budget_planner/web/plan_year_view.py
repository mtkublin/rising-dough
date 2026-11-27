"""Plan year tab and budget override dialog view models (T-UR11, ADR-0107 section 5, ADR-0136).

Everything the year grid and the override dialogs print is decided here from service values: the
cell text and its tier state, the accessible names, the dialog links, the scope radios, the hero
and the remove sentence. Tier choice stays in ``services.budget.pick_tier``. Templates only print.
No I/O, no clock.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final

from budget_planner.domain.money import format_figure, format_major
from budget_planner.services import budget as budget_service
from budget_planner.web.view_models import (
    MONTH_SHORT,
    BudgetPeriod,
    PeriodPicker,
    PickerCell,
    month_name,
)

YEAR_TAB_URL: Final = "/plan?tab=year&year="
"""Base of the year tab's period links (the year follows)."""

TIER_ONE_OFF: Final = "one-off"
TIER_RECURRING: Final = "recurring"
TIER_DEFAULT: Final = "default"
TIERS: Final = (TIER_ONE_OFF, TIER_RECURRING, TIER_DEFAULT)

_STATE: Final[Mapping[str, str]] = MappingProxyType(
    {"one_off": "one-off", "recurring": "recurring", "default": "default", "unset": "unset"}
)
_GLYPH: Final[Mapping[str, str]] = MappingProxyType(
    {"one-off": "• ", "recurring": "↻ ", "default": ""}
)
_STATE_LABEL: Final[Mapping[str, str]] = MappingProxyType(
    {
        "one-off": "one-off override",
        "recurring": "recurring override",
        "default": "default",
        "unset": "unset",
    }
)
_UNSET_TEXT: Final = "\N{EN DASH}"
_ORIGIN_LABEL: Final[Mapping[str, str]] = MappingProxyType(
    {"default": "default", "recurring": "recurring override", "one_off": "one-off override"}
)
_YEAR_SPAN: Final = 1
"""Years shown either side of the selected one in the picker."""


@dataclass(frozen=True, slots=True)
class OverrideTarget:
    """The category and month an override dialog edits."""

    category_id: int
    category_name: str
    year: int
    month: int

    @property
    def period(self) -> str:
        """``Oct 2026``."""
        return f"{MONTH_SHORT[self.month - 1]} {self.year}"

    @property
    def action(self) -> str:
        """Where both dialogs post."""
        return f"/budget/rules/{self.category_id}/overrides"

    def url(self, tier: str, *, remove: bool = False) -> str:
        """Link of the dialog (or its remove confirm) on scope ``tier``."""
        base = f"{self.action}/new?year={self.year}&month={self.month}&tier={tier}"
        return f"{base}&remove=1" if remove else base


def tier_labels(month: int) -> Mapping[str, str]:
    """Scope names shared by the dialog's radios and the year cell's chips (``every June``)."""
    return {
        TIER_ONE_OFF: "this month only",
        TIER_RECURRING: f"every {month_name(month).lower()}",
        TIER_DEFAULT: "every month (default)",
    }


_ORIGIN_TIER: Final = MappingProxyType(
    {
        "one_off": TIER_ONE_OFF,
        "recurring": TIER_RECURRING,
        "default": TIER_DEFAULT,
        "unset": TIER_DEFAULT,
    }
)


def row_tier(state: OverrideState) -> str:
    """Scope a budget row's edit dialog opens on: the tier its figure comes from (R4, R5)."""
    _, origin = budget_service.pick_tier(state.one_off, state.recurring, state.default)
    return _ORIGIN_TIER.get(origin, TIER_DEFAULT)


# --- Year grid ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class YearCell:
    """One month link of a category row: printed text, tier state and dialog link."""

    month: int
    text: str
    state: str
    label: str
    url: str
    editor_label: str  # the inline editor's field label: ``Nights Out, November budget``
    amount_text: str  # the editor's start value (empty for an unset cell)
    action: str  # where the editor posts (the override route; the two chips pick the tier)
    year: int
    recurring_label: str  # the "every <month>" chip text (the chip row is one shared template)


@dataclass(frozen=True, slots=True)
class YearRow:
    """One category row of the grid."""

    category_id: int
    category_name: str
    category_color: str | None
    cells: tuple[YearCell, ...]


@dataclass(frozen=True, slots=True)
class MonthHeader:
    """A column heading; ``current`` marks this month of the current year."""

    text: str
    current: bool


@dataclass(frozen=True, slots=True)
class Unbudgeted:
    """A category without a budget and the link that sets one."""

    category_id: int
    category_name: str
    category_color: str | None
    url: str


@dataclass(frozen=True, slots=True)
class YearPage:
    """Values of Plan · year."""

    year: int
    months: tuple[MonthHeader, ...]
    rows: tuple[YearRow, ...]
    unbudgeted: tuple[Unbudgeted, ...]
    unbudgeted_heading: str
    period: BudgetPeriod
    reload_url: str
    scope_labels: Mapping[
        str, str
    ]  # the editor's chip texts (``tier_labels``, one source with the dialog)


def _cell(
    row: budget_service.YearlyRow,
    cell: budget_service.YearlyCell,
    target: OverrideTarget,
    currency: str,
) -> YearCell:
    state = _STATE.get(cell.origin, "default")
    amount = format_figure(cell.amount_minor or 0, currency)
    if state == "unset":
        text, spoken = _UNSET_TEXT, "unset"
    else:
        text, spoken = f"{_GLYPH.get(state, '')}{amount}", f"{amount} {currency}"
    return YearCell(
        month=target.month,
        text=text,
        state=state,
        label=f"{row.category_name}, {month_name(target.month)}: {spoken}, {_STATE_LABEL[state]}",
        url=target.url(TIER_ONE_OFF),
        editor_label=f"{row.category_name}, {month_name(target.month)} budget",
        amount_text="" if state == "unset" else amount,
        action=target.action,
        year=target.year,
        recurring_label=tier_labels(target.month)[TIER_RECURRING],
    )


def _row(row: budget_service.YearlyRow, year: int, currency: str) -> YearRow:
    return YearRow(
        category_id=row.category_id,
        category_name=row.category_name,
        category_color=row.category_color,
        cells=tuple(
            _cell(
                row, cell, OverrideTarget(row.category_id, row.category_name, year, month), currency
            )
            for month, cell in enumerate(row.cells, start=1)
        ),
    )


def year_period(selected: int) -> BudgetPeriod:
    """Period nav and year picker (the years around ``selected``)."""
    years = range(selected - _YEAR_SPAN, selected + _YEAR_SPAN + 1)
    picker = PeriodPicker(
        id="period-year",
        is_year=True,
        year=selected,
        prev_year_url="",
        next_year_url="",
        cells=tuple(PickerCell(str(y), f"{YEAR_TAB_URL}{y}", y == selected) for y in years),
        note="",
    )
    return BudgetPeriod(
        label=str(selected),
        prev_url=f"{YEAR_TAB_URL}{selected - 1}",
        next_url=f"{YEAR_TAB_URL}{selected + 1}",
        picker=picker,
    )


def year_page(
    rows: tuple[budget_service.YearlyRow, ...],
    selected: int,
    *,
    current: tuple[int, int],
    currency: str,
    linkable: frozenset[int],
) -> YearPage:
    """Grid rows for categories with a budget, every other live category in the disclosure.

    A category without a budget (with or without ledger entries) is a link in the collapsed
    "N categories without a budget" list, never a grid row (R14, T-UR75). ``current`` is today's
    ``(year, month)``: it marks the column heading and picks the month a "set budget" link opens on.
    ``linkable`` holds the live category ids, the ones the set-budget dialog accepts: an archived
    category is never listed, in any year.
    """
    current_year, current_month = current
    budgeted = tuple(_row(r, selected, currency) for r in rows if r.total_minor)
    unset = tuple(
        Unbudgeted(
            r.category_id,
            r.category_name,
            r.category_color,
            OverrideTarget(r.category_id, r.category_name, selected, current_month).url(
                TIER_DEFAULT
            ),
        )
        for r in rows
        if not r.total_minor and r.category_id in linkable
    )
    noun = "category" if len(unset) == 1 else "categories"
    return YearPage(
        year=selected,
        months=tuple(
            MonthHeader(name.upper(), selected == current_year and n == current_month)
            for n, name in enumerate(MONTH_SHORT, start=1)
        ),
        rows=budgeted,
        unbudgeted=unset,
        unbudgeted_heading=f"{len(unset)} {noun} without a budget",
        period=year_period(selected),
        reload_url=f"{YEAR_TAB_URL}{selected}",
        scope_labels=tier_labels(current_month),
    )


# --- Override dialogs --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TierOption:
    """One scope radio."""

    value: str
    label: str
    checked: bool


@dataclass(frozen=True, slots=True)
class OverrideDialog:
    """Values of the standard override dialog (handoff ``override--budget-*``)."""

    target: OverrideTarget
    title: str
    hero: Mapping[str, str | None]
    tiers: tuple[TierOption, ...]
    actions: tuple[Mapping[str, str], ...]


@dataclass(frozen=True, slots=True)
class OverrideState:
    """Stored amounts of one category and month (None: no row), minor units."""

    one_off: int | None
    recurring: int | None
    default: int | None


def removable_tier(state: OverrideState, tier: str) -> str | None:
    """The override a remove action drops: the chosen scope if stored, else any month tier."""
    if tier == TIER_ONE_OFF and state.one_off is not None:
        return TIER_ONE_OFF
    if tier == TIER_RECURRING and state.recurring is not None:
        return TIER_RECURRING
    if state.one_off is not None:
        return TIER_ONE_OFF
    return TIER_RECURRING if state.recurring is not None else None


def _stored(state: OverrideState, tier: str) -> int | None:
    return {
        TIER_ONE_OFF: state.one_off,
        TIER_RECURRING: state.recurring,
        TIER_DEFAULT: state.default,
    }[tier]


def _dialog_title(target: OverrideTarget, state: OverrideState) -> str:
    """``set budget · <category>`` while nothing is stored, else ``edit budget`` with the period."""
    if state.one_off is None and state.recurring is None and state.default is None:
        return f"set budget · {target.category_name}"
    return f"edit budget · {target.category_name} · {target.period}"


def override_dialog(
    target: OverrideTarget,
    *,
    tier: str,
    state: OverrideState,
    currency: str,
    amount_text: str | None = None,
    error: str | None = None,
) -> OverrideDialog:
    """The override dialog on scope ``tier``; ``amount_text`` is a rejected entry to show again."""
    resolved, _ = budget_service.pick_tier(state.one_off, state.recurring, state.default)
    stored = _stored(state, tier)
    prefill = stored if stored is not None else resolved
    if amount_text is None:
        amount_text = "" if prefill is None else format_major(prefill, currency)
    labels = tier_labels(target.month)
    actions: list[Mapping[str, str]] = [{"tone": "cancel"}]
    dropped = removable_tier(state, tier)
    if dropped is not None:
        actions.append(
            {
                "tone": "secondary",
                "id": "override-remove",
                "label": "remove override",
                "hx_get": target.url(dropped, remove=True),
                "hx_target": "#modal-root",
                "hx_swap": "innerHTML",
            }
        )
    actions.append({"tone": "primary", "label": "[ save ]"})
    default_note = (
        None if state.default is None else f"default {format_figure(state.default, currency)}"
    )
    return OverrideDialog(
        target=target,
        title=_dialog_title(target, state),
        hero={
            "currency": currency,
            "amount_value": amount_text,
            "amount_id": "field-amount",
            "note": default_note,
            "error": error,
        },
        tiers=tuple(TierOption(t, labels[t], t == tier) for t in TIERS),
        actions=tuple(actions),
    )


@dataclass(frozen=True, slots=True)
class RemoveConfirm:
    """Values of the remove confirm (handoff ``override--remove``)."""

    target: OverrideTarget
    tier: str
    title: str
    text: str


def remove_confirm(
    target: OverrideTarget, *, tier: str, state: OverrideState, currency: str
) -> RemoveConfirm:
    """Confirm that names the amount the month falls back to once ``tier`` is dropped."""
    after_amount, origin = budget_service.pick_tier(
        None if tier == TIER_ONE_OFF else state.one_off,
        None if tier == TIER_RECURRING else state.recurring,
        state.default,
    )
    where = f"{target.category_name} · {target.period}"
    if after_amount is None:
        text = f"{where} has no budget left."
    else:
        text = (
            f"{where} goes back to the {_ORIGIN_LABEL[origin]} "
            f"{format_figure(after_amount, currency)} {currency}."
        )
    return RemoveConfirm(target=target, tier=tier, title="Remove override?", text=text)
