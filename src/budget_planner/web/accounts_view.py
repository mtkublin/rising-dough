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
from datetime import date
from typing import cast

from budget_planner.domain.accounts import Account, AccountStats
from budget_planner.domain.money import format_figure, percent_of
from budget_planner.domain.snapshots import AccountSnapshot
from budget_planner.services.account_planned import AccountPlanned
from budget_planner.services.balance import sparkline_points
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


def type_label(account_type: str | None) -> str:
    """Account type for display: free text with ``_`` shown as a space (``credit_card``)."""
    return (account_type or "").replace("_", " ")


def checked_label(snapshots: list[AccountSnapshot]) -> str:
    """Date of the newest snapshot as ``01 APR``; ``never`` when the account has none."""
    if not snapshots:
        return "never"
    return snapshot_line(snapshots[0]).taken


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
        subtitle=f"{type_label(acc.type) or 'credit'} · liability" if acc.is_liability else kind,
        currency=acc.currency,
        balance_minor=balance,
        balance_text=format_figure(balance, acc.currency),
        negative=balance < 0,
        txn_count=stats.txn_count,
        checked=checked_label(cast(list[AccountSnapshot], card["snapshots"])),
        trend=trend_view(cast(list[tuple[date, int]], card["series"]), balance),
        credit=credit_line(util) if util is not None else None,
        after_text=(
            format_figure(planned.projected_minor, acc.currency)
            if planned is not None and shows_after
            else None
        ),
        menu_id=f"account-menu-{acc.id}",
        menu_sub=f"{kind} · {format_figure(balance, acc.currency, with_currency=True)}",
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
