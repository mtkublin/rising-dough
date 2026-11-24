"""Drift test: every seed-dependent overlay row equals what the seed + services produce.

T-UR00b, ADR-0147 section 4: the overlay corrects the handoff to the app's value, never
the reverse. Each ``Case`` names an overlay row (page, selector, ``old``) and computes the
replacement through the real services over a built base seed. The test fails when a row
in ``handoff_overlay.toml`` is missing, differs from its case, or a "seed value via" row
has no case, so a seed or service change cannot leave a stale overlay value behind.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.money import format_money
from budget_planner.repositories import (
    accounts as accounts_repo,
    recurring as recurring_repo,
    users as users_repo,
)
from budget_planner.services import (
    accounts as accounts_service,
    balance as balance_service,
    budget as budget_service,
    forecast as forecast_service,
    fortune as fortune_service,
    fx as fx_service,
    ledger_totals,
    recurring_formula,
    security_settings,
    today as today_service,
)
from budget_planner.web import ledger_data, view_models
from budget_planner.web.ledger_types import LedgerFilters
from tests.visual import handoff_seed as seed
from tests.visual.frozen_server import HANDOFF_FIXTURE_DATE
from tests.visual.overlay import Row, load_rows

USER = seed.OWNER_ID
DAY = dt.date.fromisoformat(HANDOFF_FIXTURE_DATE)
NOW = dt.datetime(2026, 10, 31, 10, tzinfo=dt.UTC)
MINUS = chr(0x2212)  # handoff negative sign
DOT = "·"
ALL = "pages/*.html"


def money(minor: int, *, signed: bool = False) -> str:
    """Handoff figure: grouped, no currency, U+2212 for negatives (``+`` when ``signed``)."""
    text = format_money(abs(minor), "PLN").removesuffix(" PLN")
    if minor < 0:
        return MINUS + text
    return "+" + text if signed else text


def stamp(moment: dt.datetime, *, with_time: bool = True) -> str:
    """Handoff date label (``30 OCT 21:12`` / ``30 OCT``) in the display timezone (CET)."""
    local = moment + seed.WARSAW_OFFSET if with_time else moment
    label = f"{local:%d %b}".upper()
    return f"{label} {local:%H:%M}" if with_time else label


@dataclass(frozen=True)
class Vals:
    """Every app value the overlay rows need, from services over the built base seed."""

    per_day: int
    committed: int
    left: int
    budgeted: int
    spent: int
    unbudgeted: int
    over_count: int
    bar_label: str
    afford_small_per_day: int
    afford_small_delta: int
    afford_over_per_day: int
    afford_over_over: int
    actual_count: int
    recurring_count: int
    rec_in: int
    rec_out: int
    rec_next_due: dt.date
    txns: dict[str, int]
    checked: dict[str, dt.datetime]
    session_created: dt.datetime
    session_expires: dt.datetime
    ewa_last_seen: dt.datetime | None
    fc_delta: int
    fc_end: int
    fc_peak: int
    fc_peak_label: str
    formula_next_all: frozenset[int]


def _collect(conn: sqlite3.Connection, settings: Settings, token: str) -> Vals:
    tz = settings.display_timezone
    year, month = budget_service.fiscal_month_for(conn, USER, DAY)
    summary = budget_service.month_summary(
        conn, USER, year, month, today=DAY, base_currency="PLN", display_timezone=tz
    )
    assert summary.left_daily_spend_minor is not None
    bview = view_models.budget_view(summary, DAY)
    small = today_service.afford(conn, USER, DAY, 25_000, base_currency="PLN", display_timezone=tz)
    over = today_service.afford(conn, USER, DAY, 180_000, base_currency="PLN", display_timezone=tz)
    ctx = ledger_data.index_context(
        conn, USER, settings=settings, view="recurring", filters=LedgerFilters(), today=DAY
    )
    recurring = ctx["recurring_summary"]
    counts = ctx["tab_counts"]
    assert isinstance(recurring, ledger_totals.RecurringTotals)
    assert isinstance(counts, dict)
    accounts = accounts_repo.list_all(conn, USER)
    stats = balance_service.account_stats_many(conn, USER, accounts)
    checked = {
        r.account_name: r.last_checked_at
        for r in accounts_service.last_checked(conn, USER)
        if r.last_checked_at is not None
    }
    with clock.frozen(NOW):
        view = security_settings.security_view(
            conn,
            USER,
            session_token=token,
            absolute_lifetime_days=settings.session_absolute_lifetime_days,
        )
    (current,) = (r for r in view.session_rows if r.is_current)
    ewa = next(u for u in users_repo.list_live(conn) if u.email == "parent@example.test")
    net = fortune_service.compute_fortune(
        conn, USER, fx_service.converter_for(conn, settings, DAY)
    ).net_base
    projection = forecast_service.monthly_projection(conn, USER, settings, DAY, 12)
    fc = forecast_service.projection_summary(projection, now_value=net)
    assert fc is not None
    assert fc.end_point.end_balance_minor - net == fc.delta_minor  # the strip says "+", an increase
    fx = recurring_formula.formula_fx_for(conn, USER, settings, DAY)
    nexts = frozenset(
        recurring_formula.resolve_rule_amount(conn, USER, rule, rule.next_due, fx)
        for rule in recurring_repo.list_rules(conn, USER)
        if rule.amount_formula is not None
    )
    return Vals(
        per_day=summary.left_daily_spend_minor,
        committed=summary.totals.committed_minor,
        left=summary.totals.remaining_minor,
        budgeted=summary.totals.budgeted_minor,
        spent=summary.totals.spent_minor,
        unbudgeted=summary.totals.unbudgeted_committed_minor,
        over_count=bview.over_count,
        bar_label=view_models.bar_aria_label(bview.spent_pct, bview.left_pct),
        afford_small_per_day=small.per_day_minor,
        afford_small_delta=small.delta_minor,
        afford_over_per_day=over.unclamped_per_day_minor,
        afford_over_over=over.over_minor,
        actual_count=counts["actual"],
        recurring_count=counts["recurring"],
        rec_in=recurring.monthly_in_minor,
        rec_out=recurring.monthly_out_minor,
        rec_next_due=recurring.next_due or DAY,
        txns={a.name: stats[a.id].txn_count for a in accounts},
        checked=checked,
        session_created=current.session.created_at,
        session_expires=current.absolute_expires_at,
        ewa_last_seen=ewa.last_seen_at,
        fc_delta=fc.delta_minor,
        fc_end=fc.end_point.end_balance_minor,
        fc_peak=fc.peak_point.end_balance_minor,
        fc_peak_label=fc.peak_point.label,
        formula_next_all=nexts,
    )


@pytest.fixture(scope="module")
def vals(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Vals]:
    result = seed.build_seed(tmp_path_factory.mktemp("overlay-values") / "base.sqlite")
    settings = Settings(_env_file=None, database_url=f"sqlite:///{result.db_path.as_posix()}")
    conn = get_connection(settings)
    try:
        yield _collect(conn, settings, result.session_token)
    finally:
        conn.close()


@dataclass(frozen=True)
class Case:
    """One overlay row and the service value it must carry."""

    page: str
    select: str
    old: str
    value: Callable[[Vals], str]
    reason: str
    field: str = "text"
    count: int = 1
    optional: bool = True

    def key(self) -> tuple[str, str, str]:
        return (self.page, self.select, self.old)


def _hero_note(v: Vals) -> str:
    return (
        f"{money(v.budgeted)} budgeted {DOT} {money(v.spent)} spent {DOT} "
        f"{money(v.committed)} committed {DOT} {v.over_count} categories over {DOT} "
        f"{money(v.unbudgeted)} planned in unbudgeted categories"
    )


def _rec_note(v: Vals) -> str:
    due = f"{v.rec_next_due:%d %b}".lower()
    return f"in {money(v.rec_in, signed=True)} {DOT} {v.recurring_count} rules {DOT} next due {due}"


def _fc_note(v: Vals) -> str:
    month, year = v.fc_peak_label.lower().split()
    return (
        f"{money(v.fc_delta, signed=True)} PLN over 12 months {DOT} "
        f"peak {money(v.fc_peak)} in {month} {year}"
    )


def _txns(name: str) -> Callable[[Vals], str]:
    return lambda v: str(v.txns[name])


def _checked(name: str) -> Callable[[Vals], str]:
    return lambda v: stamp(v.checked[name], with_time=False)


_SEED = "seed value via"
_ACCOUNTS = {  # handoff order on accounts.html: index -> (name, TXNS, checked)
    1: ("Investments A", "2", "01 APR"),
    2: ("Savings", "8", "01 APR"),
    3: ("Investments C", "6", "01 JUL"),
    4: ("Checking", "84", "01 APR"),
    5: ("Investments B", "2", "01 APR"),
    6: ("Investments D", "0", "01 JUL"),
    7: ("Cash Wallet", "13", "01 APR"),
    8: ("Checking EUR", "24", "01 JUL"),
    9: ("Credit Card", "468", "01 APR"),
    10: ("Everyday Spending", "30", "01 SEP"),
}
_TXN_ROWS = (1, 2, 3, 4, 5, 7, 8, 9, 10)  # Investments D: 0 in both
_CHECKED_ROWS = (3, 7)  # Investments C and Cash Wallet carry the 29 Oct reconciliation
ARROW = "→"
UP = "▲"

CASES: tuple[Case, ...] = (
    # Today and Plan headline: committed includes the overdue "Annual insurance".
    Case(
        ALL,
        ".rd-hero__figure--xl",
        "199.99",
        lambda v: money(v.per_day),
        f"{_SEED} budget.month_summary: left per day (overdue Annual insurance is committed)",
    ),
    Case(
        ALL,
        '.rd-stats__value:-soup-contains-own("34.60")',
        "34.60",
        lambda v: money(v.committed),
        f"{_SEED} budget.month_summary: committed (overdue Annual insurance 412.00 included)",
    ),
    Case(
        ALL,
        '.rd-stats__value:-soup-contains-own("1,399.93")',
        "1,399.93",
        lambda v: money(v.left),
        f"{_SEED} budget.month_summary: left (budgeted - spent - committed)",
    ),
    Case(
        ALL,
        '[role="img"][aria-label="78 percent spent, 15 percent left"]',
        "78 percent spent, 15 percent left",
        lambda v: v.bar_label,
        f"{_SEED} view_models.bar_aria_label on budget_view (floored spent percent, "
        "left = 100 - spent); value-inventory 5 row 6",
        field="aria-label",
    ),
    Case(
        ALL,
        ".rd-afford__result:not(.rd-afford__result--over)",
        f"{ARROW} per day becomes 164.28 ",
        lambda v: f"{ARROW} per day becomes {money(v.afford_small_per_day)} ",
        f"{_SEED} today.afford(250.00): per day after the entry",
    ),
    Case(
        "pages/today--afford-over.html",
        "#afford-result .rd-afford__result--over",
        f"{UP} per day becomes {MINUS}14.20 {DOT} 114.20 over",
        lambda v: (
            f"{UP} per day becomes {money(v.afford_over_per_day)} {DOT} "
            f"{money(v.afford_over_over)} over"
        ),
        f"{_SEED} today.afford(1,800.00) (ADR-0151 semantics unchanged); the handoff is "
        "inconsistent (value-inventory 5 row 9)",
        optional=False,
    ),
    Case(
        ALL,
        ".rd-hero__figure--plan",
        "1,399.93",
        lambda v: money(v.left),
        f"{_SEED} budget.month_summary: budget left",
    ),
    Case(
        ALL,
        '.rd-hero__note > .u-hide-below-md:-soup-contains-own("6,449.08 budgeted")',
        "6,449.08 budgeted · 5,014.55 spent · 34.60 committed · 6 categories over · "
        "277.94 planned in unbudgeted categories",
        _hero_note,
        f"{_SEED} budget.month_summary and view_models.budget_view (committed, categories over)",
    ),
    Case(
        ALL,
        '.rd-hero__note > .u-hide-from-md:-soup-contains-own("34.60 committed")',
        "34.60 committed · 6 over",
        lambda v: f"{money(v.committed)} committed {DOT} {v.over_count} over",
        f"{_SEED} budget.month_summary and view_models.budget_view",
    ),
    Case(
        ALL,
        'td.rd-budget__status:-soup-contains-own("left 1,399.93")',
        "left 1,399.93",
        lambda v: f"left {money(v.left)}",
        f"{_SEED} budget.month_summary: left",
    ),
    # Ledger tab counts and recurring hero.
    Case(
        ALL,
        'a.rd-tabs__tab:-soup-contains-own("actual 616")',
        "actual 616",
        lambda v: f"actual {v.actual_count}",
        f"{_SEED} ledger_data tab_counts (transactions.count_filtered)",
    ),
    Case(
        ALL,
        'a.rd-tabs__tab:-soup-contains-own("recurring 27")',
        "recurring 27",
        lambda v: f"recurring {v.recurring_count}",
        f"{_SEED} ledger_data tab_counts (recurring.list_rules, active)",
    ),
    Case(
        ALL,
        '.rd-hero__figure--wide:-soup-contains-own("13,755.41")',
        f"{MINUS}13,755.41",
        lambda v: money(-v.rec_out),
        f"{_SEED} ledger_totals.recurring_monthly_totals: monthly out",
    ),
    Case(
        ALL,
        '.rd-hero__note:-soup-contains-own("27 rules")',
        "in +23,253.18 · 27 rules · next due 01 nov",
        _rec_note,
        f"{_SEED} ledger_totals.recurring_monthly_totals: monthly in, rule count, next due",
    ),
    Case(
        ALL,
        ".rd-formula__next",
        f"{ARROW} next amount 1,836.93 PLN",
        lambda v: f"{ARROW} next amount {money(next(iter(v.formula_next_all)))} PLN",
        f"{_SEED} recurring_formula.resolve_rule_amount: the seed's formula rules all "
        "evaluate to one amount for their next occurrence",
        count=4,
    ),
    # Accounts: TXNS counts and the checked dates of the two reconciled accounts.
    *(
        Case(
            ALL,
            f".rd-row--account:nth-of-type({i}) .rd-account__txns",
            _ACCOUNTS[i][1],
            _txns(_ACCOUNTS[i][0]),
            f"{_SEED} balance.account_stats_many: {_ACCOUNTS[i][0]} txn_count",
        )
        for i in _TXN_ROWS
    ),
    *(
        Case(
            ALL,
            f".rd-row--account:nth-of-type({i}) .rd-account__checked",
            _ACCOUNTS[i][2],
            _checked(_ACCOUNTS[i][0]),
            f"{_SEED} accounts.last_checked: {_ACCOUNTS[i][0]} counts the 29 Oct reconciliation",
        )
        for i in _CHECKED_ROWS
    ),
    # Security sessions, users, forecast strip.
    Case(
        "pages/settings/security*.html",
        '.rd-row--session td:-soup-contains-own("12 NOV 09:14")',
        "12 NOV 09:14",
        lambda v: stamp(v.session_created),
        f"{_SEED} security_settings.security_view: the owner's session start (seed clock)",
    ),
    Case(
        "pages/settings/security*.html",
        '.rd-row--session td:-soup-contains-own("12 DEC")',
        "12 DEC",
        lambda v: stamp(v.session_expires, with_time=False),
        f"{_SEED} security_settings.security_view: absolute expiry (start + 30 days)",
    ),
    Case(
        ALL,
        'tr.rd-row--user td:-soup-contains-own("12 NOV 08:40")',
        "12 NOV 08:40",
        lambda v: "\u2014" if v.ewa_last_seen is None else stamp(v.ewa_last_seen),
        f"{_SEED} users.list_live: Ewa never signed in (last_seen_at is empty)",
    ),
    Case(
        "pages/plan/forecast.html",
        ".rd-hero__figure--wide",
        "79,047.79",
        lambda v: money(v.fc_end),
        f"{_SEED} forecast.projection_summary: end balance of the 12-month projection",
        optional=False,
    ),
    Case(
        "pages/plan/forecast.html",
        ".rd-hero__note",
        "+46,320.57 PLN over 12 months · peak 86,239.67 in aug 2027",
        _fc_note,
        f"{_SEED} forecast.projection_summary: delta from net worth (NOW), peak month",
        optional=False,
    ),
)


ROWS = load_rows()


def _row_for(case: Case) -> Row | None:
    return next(
        (r for r in ROWS if (r.page, r.select, r.old) == case.key()),
        None,
    )


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c.page}:{c.select}"[:80])
def test_row_carries_the_service_value(case: Case, vals: Vals) -> None:
    row = _row_for(case)
    assert row is not None, f"no overlay row for {case.key()}"
    assert row.value == case.value(vals)
    assert (row.field, row.count, row.optional) == (case.field, case.count, case.optional)
    assert row.reason == case.reason
    assert row.reason.startswith(_SEED) or "seed value via" in row.reason


def test_every_seed_value_row_has_a_case() -> None:
    keys = {c.key() for c in CASES}
    claimed = [r for r in ROWS if "seed value via" in r.reason]
    assert [r for r in claimed if (r.page, r.select, r.old) not in keys] == []
    assert len(claimed) == len(CASES)


def test_unchanged_account_rows_already_match_the_seed(vals: Vals) -> None:
    """Rows left out of the overlay (TXNS, checked) are equal in handoff and seed."""
    for index, (name, txns, checked) in _ACCOUNTS.items():
        if index not in _TXN_ROWS:
            assert str(vals.txns[name]) == txns, name
        if index not in _CHECKED_ROWS:
            assert stamp(vals.checked[name], with_time=False) == checked, name


def test_overlay_values_pin(vals: Vals) -> None:
    """The figures the rows must reach (seed run), so a silent service change is visible."""
    assert (vals.committed, vals.left, vals.per_day) == (44_660, 98_793, 14_113)
    assert (vals.afford_small_per_day, vals.afford_small_delta) == (10_542, -3_571)
    assert (vals.afford_over_per_day, vals.afford_over_over) == (-11_601, 81_207)
    assert (vals.actual_count, vals.recurring_count) == (26, 15)
    assert len(vals.formula_next_all) == 1
