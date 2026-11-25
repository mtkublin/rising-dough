"""Accounts view-model values (T-Q256, Q-070, T-UR08).

One owner for credit-card utilisation so the card, the table row, the index
and the reconcile modal render the same precomputed numbers instead of doing
arithmetic in templates; also the handoff accounts page values (hero, row,
trend polyline). The percentage comes from the canonical
``domain.money.percent_of`` (whole percent, floored).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import cast

from budget_planner.domain.accounts import Account, AccountReferences, AccountStats
from budget_planner.domain.money import (
    ISO_4217_CURRENCIES,
    format_figure,
    format_major,
    format_money,
    percent_of,
)
from budget_planner.domain.snapshots import AccountSnapshot
from budget_planner.services.account_planned import AccountPlanned
from budget_planner.services.balance import sparkline_points
from budget_planner.web.paths import DELETE_PATH, EDIT_PATH
from budget_planner.web.view_models import ROW_BAR_CELLS, BarSpans, HeroFit, bar_spans, hero_fit

_FULL_BAR_PCT = 100
_SPARKLINE_WIDTH = 120
_SPARKLINE_HEIGHT = 32


@dataclass(frozen=True)
class CreditUtilisation:
    """Utilisation of a credit limit. Amounts are minor units, percents whole."""

    limit_minor: int
    used_minor: int
    available_minor: int
    over_limit_minor: int
    used_pct: int
    bar_pct: int


def credit_utilisation(account: Account, balance_minor: int) -> CreditUtilisation | None:
    """Utilisation for a liability with a positive credit limit, else ``None``.

    ``balance_minor`` is the derived balance (negative when money is owed).
    """
    limit = account.credit_limit_minor or 0
    if not account.is_liability or limit <= 0:
        return None
    used = max(-balance_minor, 0)
    used_pct = percent_of(used, limit)
    return CreditUtilisation(
        limit_minor=limit,
        used_minor=used,
        available_minor=max(limit - used, 0),
        over_limit_minor=max(used - limit, 0),
        used_pct=used_pct,
        bar_pct=min(used_pct, _FULL_BAR_PCT),
    )


def sparkline_fields(series: list[tuple[date, int]]) -> dict[str, object]:
    """Precomputed sparkline template values for one balance series (no template math)."""
    values = [v for _, v in series]
    points = sparkline_points(values, width=_SPARKLINE_WIDTH, height=_SPARKLINE_HEIGHT)
    area = (
        f"0,{_SPARKLINE_HEIGHT} {points} {_SPARKLINE_WIDTH},{_SPARKLINE_HEIGHT}" if points else ""
    )
    return {
        "sparkline_points": points,
        "sparkline_values": values,
        "sparkline_area_points": area,
        "sparkline_width": _SPARKLINE_WIDTH,
        "sparkline_height": _SPARKLINE_HEIGHT,
    }


# --- T-UR08: handoff accounts page view-models --------------------------------
_TREND_WIDTH = 100
_TREND_HEIGHT = 28
_TREND_MARGIN = 2
_TREND_POINTS = 11
_TREND_PLOT_HEIGHT = _TREND_HEIGHT - 2 * _TREND_MARGIN


@dataclass(frozen=True, slots=True)
class TrendView:
    """Sparkline polyline for the handoff 100x28 box (``charts/sparkline``)."""

    points: str
    negative: bool
    width: int = _TREND_WIDTH
    height: int = _TREND_HEIGHT
    margin: int = _TREND_MARGIN


def trend_view(series: list[tuple[date, int]], balance_minor: int) -> TrendView:
    """At most 11 evenly spaced points (x every 10), y inverted inside a 2 px margin.

    The polyline is drawn in a ``margin``-translated group, so ``points`` are plain
    ``x,y`` pairs of ``sparkline_points``; a series under two points yields no line.
    """
    values = [v for _, v in series]
    last = len(values) - 1
    if last + 1 > _TREND_POINTS:
        values = [values[int(i * last / (_TREND_POINTS - 1))] for i in range(_TREND_POINTS)]
    points = sparkline_points(values, width=_TREND_WIDTH, height=_TREND_PLOT_HEIGHT)
    return TrendView(points=points, negative=balance_minor < 0)


@dataclass(frozen=True, slots=True)
class CreditLine:
    """``used 16% \u00b7 available X of LIMIT`` with its 10-cell block bar."""

    used_pct: int
    available_minor: int
    limit_minor: int
    bar: BarSpans


def credit_line(util: CreditUtilisation) -> CreditLine:
    return CreditLine(
        used_pct=util.used_pct,
        available_minor=util.available_minor,
        limit_minor=util.limit_minor,
        bar=bar_spans(util.bar_pct, ROW_BAR_CELLS, is_over=util.over_limit_minor > 0),
    )


@dataclass(frozen=True, slots=True)
class AccountRow:
    """Everything one ``rows/account-row`` prints; the template does no logic."""

    id: int
    name: str
    kind: str
    subtitle: str
    currency: str
    balance_minor: int
    balance_text: str
    negative: bool
    txn_count: int
    checked: str
    trend: TrendView
    credit: CreditLine | None
    after_text: str | None
    menu_id: str
    menu_sub: str
    menu_items: tuple[dict[str, object], ...]


def type_label(account_type: str | None) -> str:
    """Account type for display: free text with ``_`` shown as a space (``credit_card``)."""
    return (account_type or "").replace("_", " ")


def checked_label(checked_at: datetime | None) -> str:
    """Newest snapshot or reconciliation as ``01 APR``; ``never`` when the account has none."""
    return "never" if checked_at is None else checked_at.strftime("%d %b").upper()


def account_row(card: Mapping[str, object]) -> AccountRow:
    """Row view-model from one ``accounts_data.card_context`` dict."""
    acc = cast(Account, card["account"])
    balance = cast(int, card["balance"])
    stats = cast(AccountStats, card["stats"])
    planned = cast(AccountPlanned | None, card["planned"])
    util = cast(CreditUtilisation | None, card["utilisation"])
    kind = "liability" if acc.is_liability else (type_label(acc.type) or "account")
    shows_after = planned is not None and planned.net_minor != 0
    return AccountRow(
        id=acc.id,
        name=acc.name,
        kind=kind,
        subtitle=f"{type_label(acc.type) or 'credit card'} · liability"
        if acc.is_liability
        else kind,
        currency=acc.currency,
        balance_minor=balance,
        balance_text=format_figure(balance, acc.currency),
        negative=balance < 0,
        txn_count=stats.txn_count,
        checked=checked_label(cast("datetime | None", card["checked_at"])),
        trend=trend_view(cast(list[tuple[date, int]], card["series"]), balance),
        credit=credit_line(util) if util is not None else None,
        after_text=(
            format_figure(planned.projected_minor, acc.currency)
            if planned is not None and shows_after
            else None
        ),
        menu_id=f"account-menu-{acc.id}",
        menu_sub=f"{kind} · {format_figure(balance, acc.currency, with_currency=True)}",
        menu_items=(
            {"label": "reconcile", "hx_get": f"/accounts/{acc.id}/reconcile", "phone": True},
            {"label": "edit", "hx_get": f"/accounts/{acc.id}{EDIT_PATH}"},
            {
                "label": "delete",
                "hx_get": f"/accounts/{acc.id}{EDIT_PATH}?intent=delete",
                "danger": True,
            },
        ),
    )


@dataclass(frozen=True, slots=True)
class AccountsHero:
    """Net-worth hero figures (base currency) as printed text."""

    count: int
    fit: HeroFit
    net_text: str
    assets_text: str
    liabilities_text: str
    planned_text: str


def accounts_hero(
    *,
    count: int,
    net_minor: int,
    assets_minor: int,
    liabilities_minor: int,
    planned_minor: int,
    currency: str,
) -> AccountsHero:
    """Hero values; ``liabilities_minor`` is the stored (positive) owed amount, shown negative."""
    return AccountsHero(
        count=count,
        fit=hero_fit(net_minor, currency),
        net_text=format_figure(net_minor, currency),
        assets_text=format_figure(assets_minor, currency),
        liabilities_text=format_figure(-liabilities_minor, currency),
        planned_text=format_figure(planned_minor, currency, plus=True),
    )


@dataclass(frozen=True, slots=True)
class SnapshotLine:
    """One ``rows/reconcile-snapshot`` line: ``01 APR`` and the snapshot balance."""

    taken: str
    amount_minor: int


def snapshot_line(snapshot: AccountSnapshot) -> SnapshotLine:
    return SnapshotLine(
        taken=snapshot.taken_at.strftime("%d %b").upper(), amount_minor=snapshot.balance
    )


# --- T-UR08b: account dialogs (new, edit, delete) ------------------------------
ACCOUNT_TYPES = ("bank", "cash", "savings", "investment", "credit card")


@dataclass(frozen=True, slots=True)
class TypeOption:
    value: str
    label: str
    selected: bool


@dataclass(frozen=True, slots=True)
class AccountDialog:
    """Everything ``dialog-account`` prints for the new and edit dialogs (no template logic)."""

    editing: bool
    dialog_id: str
    title: str
    action: str
    target: str
    swap: str
    submit_label: str
    hero: dict[str, object] | None
    name: str
    currency: str
    type_options: tuple[TypeOption, ...]
    is_liability: bool
    credit_limit: str
    liability_hint: str
    as_of: str  # ISO date the opening balance is as of (the day of creation); "" when editing


def _type_options(selected: str) -> tuple[TypeOption, ...]:
    values = list(ACCOUNT_TYPES)
    if selected and selected not in values:
        values.append(selected)
    options = [TypeOption(v, type_label(v), v == selected) for v in values]
    if not selected:
        options.insert(0, TypeOption("", "none", True))
    return tuple(options)


def _new_dialog(
    entered: Mapping[str, str], problems: Mapping[str, str], base: str, today: date
) -> AccountDialog:
    currency = entered.get("currency", "")
    typed = currency.strip().upper()
    hero: dict[str, object] = {
        # the chip follows a known typed code (an unknown one shows in the field error)
        "currency": typed if typed in ISO_4217_CURRENCIES else base,
        "amount_value": entered.get("opening_balance", "0.00"),
        "amount_label": "Opening balance",
        "amount_id": "field-opening_balance",
        "amount_name": "opening_balance",
        "note": "opening balance",
        "error": problems.get("opening_balance"),
    }
    return AccountDialog(
        editing=False,
        dialog_id="new-account",
        title="new account",
        action="/accounts",
        target="#account-form",
        swap="outerHTML",
        submit_label="[ create account ]",
        hero=hero,
        name=entered.get("name", ""),
        currency=currency,
        type_options=_type_options(entered.get("type", "bank")),
        is_liability=entered.get("is_liability", "") == "on",
        credit_limit=entered.get("credit_limit", ""),
        liability_hint="",
        as_of=today.isoformat(),
    )


def _edit_dialog(acc: Account, entered: Mapping[str, str], txn_count: int) -> AccountDialog:
    limit = format_major(acc.credit_limit_minor, acc.currency) if acc.credit_limit_minor else ""
    plural = "" if txn_count == 1 else "s"
    hint = f"\u25b2 {txn_count} transaction{plural}: this balance will count against net worth."
    return AccountDialog(
        editing=True,
        dialog_id="edit-account",
        title=f"edit account \u00b7 {acc.name}",
        action=f"/accounts/{acc.id}",
        target=f"#account-{acc.id}",
        swap="outerHTML",
        submit_label="[ save ]",
        hero=None,
        name=entered.get("name", acc.name),
        currency=acc.currency,
        type_options=_type_options(entered.get("type", acc.type or "")),
        is_liability=entered.get("is_liability", "on" if acc.is_liability else "") == "on",
        credit_limit=entered.get("credit_limit", limit),
        liability_hint=hint,
        as_of="",
    )


def account_dialog(
    acc: Account | None,
    *,
    values: Mapping[str, str] | None = None,
    base_currency: str,
    today: date,
    txn_count: int = 0,
    errors: Mapping[str, str] | None = None,
) -> AccountDialog:
    """New (``acc`` is ``None``) or edit dialog values; ``values`` refill a rejected submit."""
    entered = values or {}
    if acc is None:
        return _new_dialog(entered, errors or {}, base_currency, today)
    return _edit_dialog(acc, entered, txn_count)


@dataclass(frozen=True, slots=True)
class DeleteDialog:
    """The delete confirm or one of its blocked variants (handoff ``delete-account*``)."""

    blocked: bool
    title: str
    text: str
    action: str
    link_label: str
    link_href: str


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


def _blocked(acc: Account, refs: AccountReferences, balance_minor: int) -> DeleteDialog:
    action = f"/accounts/{acc.id}{DELETE_PATH}"
    ledger = f"/ledger?account_id={acc.id}"
    title = f"Can\u2019t delete {acc.name}"
    items = []
    if refs.planned:
        items.append(_count(refs.planned, "planned item"))
    if refs.recurring:
        items.append(_count(refs.recurring, "recurring rule"))
    if refs.transactions:
        extra = f" and {' and '.join(items)}" if items else ""
        text = f"It still has {_count(refs.transactions, 'transaction')}{extra}."
        label = f"view {_count(refs.transactions, 'transaction')}"
        return DeleteDialog(
            True,
            title,
            f"{text} Move or delete them first.",
            action,
            label,
            f"{ledger}&view=actual",
        )
    if items:
        verb = "uses" if refs.planned + refs.recurring == 1 else "use"
        text = f"It has no transactions, but {' and '.join(items)} still {verb} it."
        only_rules = bool(refs.recurring) and not refs.planned
        view = "recurring" if only_rules else "planned"
        label = "view recurring rules" if only_rules else "view planned items"
        return DeleteDialog(
            True,
            title,
            f"{text} Move or delete them first.",
            action,
            label,
            f"{ledger}&view={view}",
        )
    figure = format_figure(balance_minor, acc.currency, with_currency=True)
    return DeleteDialog(
        True, title, f"Its balance is {figure}. Bring it to zero first.", action, "", ""
    )


def delete_dialog(acc: Account, refs: AccountReferences, balance_minor: int) -> DeleteDialog:
    """Confirm when nothing points at the account, else the blocked variant with counts.

    Mirrors ``services.accounts.archive_account``: a non-zero balance or any live
    transaction, planned or recurring row blocks the delete.
    """
    if refs.transactions or refs.planned or refs.recurring or balance_minor:
        return _blocked(acc, refs, balance_minor)
    return DeleteDialog(
        blocked=False,
        title=f"Delete {acc.name}?",
        text="Nothing points at it: no transactions, planned or recurring items. "
        "This can\u2019t be undone.",
        action=f"/accounts/{acc.id}{DELETE_PATH}",
        link_label="",
        link_href="",
    )


# --- T-UR08b: reconcile dialog ----------------------------------------------------
@dataclass(frozen=True, slots=True)
class CategoryChoice:
    value: str
    label: str
    selected: bool


@dataclass(frozen=True, slots=True)
class ReconcileDialog:
    """Everything ``dialog-reconcile`` prints: the signed difference hero, facts and form."""

    title: str
    action: str
    preview_url: str
    target: str
    currency: str
    difference_text: str
    facts_text: str
    field_label: str
    hint: str
    hint_id: str
    value: str
    categories: tuple[CategoryChoice, ...]
    save_snapshot: bool
    snapshots: tuple[SnapshotLine, ...]


def reconcile_dialog(
    acc: Account,
    *,
    current_minor: int,
    difference_minor: int,
    value: str,
    credit: CreditUtilisation | None,
    categories: list[tuple[int, str]],
    category_id: str,
    save_snapshot: bool,
    snapshots: list[AccountSnapshot],
) -> ReconcileDialog:
    """Reconcile dialog values; ``credit`` is set when reconciling by available credit."""
    ccy = acc.currency
    if credit is None:
        field_label, hint = "balance in your bank", ""
    else:
        field_label = "remaining balance in your bank"
        hint = (
            "enter what you can still spend (limit \u2212 spent). "
            f"Limit {format_money(credit.limit_minor, ccy)} \u00b7 "
            f"implied used {format_money(credit.used_minor, ccy)}"
        )
    choices = [CategoryChoice("", "\u00b1ADJUST \u00b7 Reconciliation (system)", category_id == "")]
    choices += [
        CategoryChoice(str(cid), label, category_id == str(cid)) for cid, label in categories
    ]
    return ReconcileDialog(
        title=f"reconcile \u00b7 {acc.name}",
        action=f"/accounts/{acc.id}/reconcile",
        preview_url=f"/accounts/{acc.id}/reconcile?preview=1",
        target=f"#account-{acc.id}",
        currency=ccy,
        difference_text=format_figure(difference_minor, ccy, plus=True),
        facts_text=format_money(current_minor, ccy),
        field_label=field_label,
        hint=hint,
        hint_id="rec-available-help",
        value=value,
        categories=tuple(choices),
        save_snapshot=save_snapshot,
        snapshots=tuple(snapshot_line(s) for s in snapshots),
    )
