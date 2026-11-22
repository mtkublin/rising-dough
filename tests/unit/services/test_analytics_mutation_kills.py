"""Mutation-kill tests for ``services/analytics`` (T-Q247, ADR-0131).

Builds on the two-user and tombstone worlds from ``conftest.py`` (T-Q221), asserts exact minor-unit
values and period bounds, and injects ``today`` (no real clock).
Complements ``test_analytics_bundle.py``.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from budget_planner.services import analytics as analytics_svc, fx as fx_svc
from tests.unit.services.conftest import (
    OTHER_ID,
    OWNER_ID,
    WORLD_DAY,
    WORLD_TODAY,
    World,
    txn_amount,
)

NOV = date(2026, 11, 12)


def _conv(*rates: tuple[str, date, str]) -> fx_svc.FxConverter:
    return fx_svc.build_converter("PLN", NOV, [(c, d, Decimal(r)) for c, d, r in rates])


def _txn(
    conn: sqlite3.Connection,
    user_id: int,
    *,
    on: date,
    category_id: int,
    account_id: int,
    amount: int,
    description: str = "",
) -> int:
    return transactions_repo.create(
        conn,
        user_id,
        NewTransaction(
            operation_date=on,
            category_id=category_id,
            account_id=account_id,
            amount=amount,
            description=description,
        ),
    ).id


def _cat(conn: sqlite3.Connection, name: str, direction: Direction) -> int:
    return categories_repo.create(conn, OWNER_ID, NewCategory(name=name, direction=direction)).id


# --- bounds --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("today", "period", "start", "end"),
    [
        (date(2026, 11, 12), "month", date(2026, 11, 1), date(2026, 11, 30)),
        (date(2026, 2, 3), "month", date(2026, 2, 1), date(2026, 2, 28)),
        (date(2026, 11, 12), "year", date(2026, 1, 1), date(2026, 12, 31)),
        (date(2026, 11, 12), "trailing-12", date(2025, 12, 1), date(2026, 11, 30)),
        (date(2026, 12, 5), "trailing-12", date(2026, 1, 1), date(2026, 12, 31)),
        (date(2026, 1, 15), "trailing-12", date(2025, 2, 1), date(2026, 1, 31)),
        (date(2026, 2, 20), "trailing-12", date(2025, 3, 1), date(2026, 2, 28)),
    ],
)
def test_period_bounds(
    conn: sqlite3.Connection, today: date, period: analytics_svc.Period, start: date, end: date
) -> None:
    data = analytics_svc.bundle(conn, OWNER_ID, _conv(), today=today, period=period)
    assert (data.period, data.period_start, data.period_end) == (period, start, end)


def test_bundle_defaults_to_month_and_three_largest(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    owner = world_with_two_users.owner
    for i, amt in enumerate((10, 40, 30, 20), start=1):
        _txn(
            conn,
            OWNER_ID,
            on=date(2026, 11, i),
            category_id=owner.category_id,
            account_id=owner.account_id,
            amount=amt,
        )
    data = analytics_svc.bundle(conn, OWNER_ID, _conv(), today=WORLD_TODAY)
    assert data.period == "month"
    assert [i.amount_minor for i in data.largest_items] == [1_000, 40, 30]


# --- spend by category ---------------------------------------------------------------------------


def test_spend_by_category_is_scoped_and_ignores_tombstones(
    conn: sqlite3.Connection, world_with_tombstones: World
) -> None:
    owner = world_with_tombstones.owner
    data = analytics_svc.bundle(conn, OWNER_ID, _conv(), today=WORLD_TODAY, period="month")
    assert [(r.category_id, r.category_name, r.amount_minor) for r in data.spend_by_category] == [
        (owner.category_id, "cat-1", txn_amount(OWNER_ID))
    ]
    assert analytics_svc.spend_total_minor(data) == txn_amount(OWNER_ID)
    other = analytics_svc.bundle(conn, OTHER_ID, _conv(), today=WORLD_TODAY, period="month")
    assert [(r.category_name, r.amount_minor) for r in other.spend_by_category] == [
        ("cat-2", txn_amount(OTHER_ID))
    ]


def test_spend_window_is_inclusive_on_both_ends(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    owner = world_with_two_users.owner
    for on, amt in (
        (date(2026, 10, 31), 1),
        (date(2026, 11, 1), 10),
        (date(2026, 11, 30), 100),
        (date(2026, 12, 1), 1_000_000),
    ):
        _txn(
            conn,
            OWNER_ID,
            on=on,
            category_id=owner.category_id,
            account_id=owner.account_id,
            amount=amt,
        )
    data = analytics_svc.bundle(conn, OWNER_ID, _conv(), today=WORLD_TODAY, period="month")
    assert analytics_svc.spend_total_minor(data) == 1_000 + 10 + 100


def test_spend_sorted_by_amount_desc_then_name_casefold(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    owner = world_with_two_users.owner
    ids = {n: _cat(conn, n, Direction.EXPENSE) for n in ("b-tie", "A-tie", "big", "small")}
    for name, amt in (("b-tie", 500), ("A-tie", 500), ("big", 9_000), ("small", 5)):
        _txn(
            conn,
            OWNER_ID,
            on=WORLD_DAY,
            category_id=ids[name],
            account_id=owner.account_id,
            amount=amt,
        )
    data = analytics_svc.bundle(conn, OWNER_ID, _conv(), today=WORLD_TODAY, period="month")
    assert [(r.category_name, r.amount_minor) for r in data.spend_by_category] == [
        ("big", 9_000),
        ("cat-1", 1_000),
        ("A-tie", 500),
        ("b-tie", 500),
        ("small", 5),
    ]


def test_spend_excludes_income_and_transit_categories(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    owner = world_with_two_users.owner
    _txn(
        conn,
        OWNER_ID,
        on=WORLD_DAY,
        category_id=owner.income_category_id,
        account_id=owner.account_id,
        amount=70_000,
    )
    data = analytics_svc.bundle(conn, OWNER_ID, _conv(), today=WORLD_TODAY, period="month")
    assert [r.category_id for r in data.spend_by_category] == [owner.category_id]
    assert [i.amount_minor for i in data.largest_items] == [1_000]


def test_soft_deleted_category_keeps_its_name(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    owner = world_with_two_users.owner
    gone = _cat(conn, "gone", Direction.EXPENSE)
    _txn(
        conn,
        OWNER_ID,
        on=WORLD_DAY,
        category_id=gone,
        account_id=owner.account_id,
        amount=2_000,
        description="kept",
    )
    categories_repo.soft_delete(conn, OWNER_ID, gone)
    data = analytics_svc.bundle(conn, OWNER_ID, _conv(), today=WORLD_TODAY, period="month")
    assert data.spend_by_category[0].category_name == "gone"
    assert data.largest_items[0].category_name == "gone"
    assert data.twelve_month_averages[0].category_name == "gone"


# --- twelve-month averages -----------------------------------------------------------------------


def test_twelve_month_average_divides_by_twelve_half_even(
    conn: sqlite3.Connection, world_with_tombstones: World
) -> None:
    owner = world_with_tombstones.owner
    cat = _cat(conn, "avg", Direction.EXPENSE)
    # 30 total -> 2.5 -> HALF_EVEN 2 ; 18 total on another category -> 1.5 -> 2
    cat2 = _cat(conn, "avg2", Direction.EXPENSE)
    for on, amt, c in (
        (date(2025, 12, 1), 10, cat),  # first day of the window
        (date(2026, 11, 30), 20, cat),  # last day of the window
        (date(2025, 11, 30), 5_000_000, cat),  # one day before the window
        (date(2026, 12, 1), 5_000_000, cat),  # one day after the window
        (date(2026, 3, 3), 18, cat2),
    ):
        _txn(conn, OWNER_ID, on=on, category_id=c, account_id=owner.account_id, amount=amt)
    data = analytics_svc.bundle(conn, OWNER_ID, _conv(), today=WORLD_TODAY, period="month")
    avg = analytics_svc.twelve_month_avg_by_category(data)
    assert avg == {owner.category_id: 83, cat: 2, cat2: 2}  # 1_000/12 = 83.33
    assert [r.category_name for r in data.twelve_month_averages] == ["cat-1", "avg", "avg2"]


def test_twelve_month_average_ignores_selected_period(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    month = analytics_svc.bundle(conn, OWNER_ID, _conv(), today=WORLD_TODAY, period="month")
    year = analytics_svc.bundle(conn, OWNER_ID, _conv(), today=WORLD_TODAY, period="year")
    assert month.twelve_month_averages == year.twelve_month_averages
    assert month.income_vs_expense_monthly == year.income_vs_expense_monthly


# --- income vs expense ---------------------------------------------------------------------------


def test_monthly_flow_sorted_with_year_boundary_and_scoped(
    conn: sqlite3.Connection, world_with_tombstones: World
) -> None:
    owner = world_with_tombstones.owner
    transit = _cat(conn, "transit", Direction.TRANSIT)
    for on, c, amt in (
        (date(2026, 1, 5), owner.category_id, 300),
        (date(2025, 12, 31), owner.category_id, 200),
        (date(2025, 12, 1), owner.income_category_id, 9_000),
        (date(2025, 12, 2), owner.income_category_id, 1_000),
        (date(2026, 1, 6), transit, 77_777),
        (date(2025, 11, 30), owner.category_id, 50_000),  # before the window
    ):
        _txn(conn, OWNER_ID, on=on, category_id=c, account_id=owner.account_id, amount=amt)
    data = analytics_svc.bundle(conn, OWNER_ID, _conv(), today=WORLD_TODAY, period="month")
    flows = [
        (m.year, m.month, m.income_minor, m.expense_minor, m.label)
        for m in data.income_vs_expense_monthly
    ]
    assert flows == [
        (2025, 12, 10_000, 200, "2025-12"),
        (2026, 1, 0, 300, "2026-01"),
        (2026, 11, 0, 1_000, "2026-11"),
    ]


# --- largest items -------------------------------------------------------------------------------


def test_largest_items_order_limit_and_fields(
    conn: sqlite3.Connection, world_with_tombstones: World
) -> None:
    owner = world_with_tombstones.owner
    early = _txn(
        conn,
        OWNER_ID,
        on=date(2026, 11, 2),
        category_id=owner.category_id,
        account_id=owner.account_id,
        amount=5_000,
        description="early",
    )
    late = _txn(
        conn,
        OWNER_ID,
        on=date(2026, 11, 20),
        category_id=owner.category_id,
        account_id=owner.account_id,
        amount=5_000,
        description="late",
    )
    top = _txn(
        conn,
        OWNER_ID,
        on=date(2026, 11, 9),
        category_id=owner.category_id,
        account_id=owner.account_id,
        amount=8_000,
        description="top",
    )
    data = analytics_svc.bundle(
        conn, OWNER_ID, _conv(), today=WORLD_TODAY, period="month", largest_limit=3
    )
    assert [
        (i.transaction_id, i.operation_date, i.description, i.amount_minor)
        for i in data.largest_items
    ] == [
        (top, date(2026, 11, 9), "top", 8_000),
        (early, date(2026, 11, 2), "early", 5_000),
        (late, date(2026, 11, 20), "late", 5_000),
    ]
    assert {i.category_name for i in data.largest_items} == {"cat-1"}
    one = analytics_svc.bundle(
        conn, OWNER_ID, _conv(), today=WORLD_TODAY, period="month", largest_limit=1
    )
    assert [i.transaction_id for i in one.largest_items] == [top]
    none = analytics_svc.bundle(
        conn, OWNER_ID, _conv(), today=WORLD_TODAY, period="month", largest_limit=0
    )
    assert none.largest_items == ()


def test_largest_items_rank_by_base_amount_not_native(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    owner = world_with_two_users.owner
    eur = accounts_repo.create(
        conn, OWNER_ID, NewAccount(name="eur", currency="EUR", opening_balance=0)
    ).id
    big_native = _txn(
        conn, OWNER_ID, on=WORLD_DAY, category_id=owner.category_id, account_id=eur, amount=2_000
    )
    pln = _txn(
        conn,
        OWNER_ID,
        on=WORLD_DAY,
        category_id=owner.category_id,
        account_id=owner.account_id,
        amount=5_000,
    )
    conv = _conv(("EUR", date(2026, 11, 1), "4.00"), ("EUR", date(2026, 11, 11), "5.00"))
    data = analytics_svc.bundle(conn, OWNER_ID, conv, today=WORLD_TODAY, period="month")
    # 2_000 EUR on 2026-11-10 uses the 2026-11-01 rate (4.00), not the later 5.00.
    assert [(i.transaction_id, i.amount_minor) for i in data.largest_items] == [
        (big_native, 8_000),
        (pln, 5_000),
        (world_with_two_users.owner.transaction_id, 1_000),
    ]
    assert analytics_svc.spend_total_minor(data) == 14_000


def test_foreign_amount_uses_each_transaction_date_rate(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    owner = world_with_two_users.owner
    eur = accounts_repo.create(
        conn, OWNER_ID, NewAccount(name="eur", currency="EUR", opening_balance=0)
    ).id
    _txn(
        conn,
        OWNER_ID,
        on=date(2026, 11, 3),
        category_id=owner.category_id,
        account_id=eur,
        amount=100,
    )
    _txn(
        conn,
        OWNER_ID,
        on=date(2026, 11, 8),
        category_id=owner.category_id,
        account_id=eur,
        amount=100,
    )
    conv = _conv(("EUR", date(2026, 11, 1), "4.00"), ("EUR", date(2026, 11, 5), "4.50"))
    data = analytics_svc.bundle(conn, OWNER_ID, conv, today=WORLD_TODAY, period="month")
    assert analytics_svc.spend_total_minor(data) == 1_000 + 400 + 450
    flow = data.income_vs_expense_monthly[0]
    assert flow.expense_minor == 1_850


def test_missing_rate_for_an_account_currency_raises(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    owner = world_with_two_users.owner
    eur = accounts_repo.create(
        conn, OWNER_ID, NewAccount(name="eur", currency="EUR", opening_balance=0)
    ).id
    _txn(conn, OWNER_ID, on=WORLD_DAY, category_id=owner.category_id, account_id=eur, amount=1)
    with pytest.raises(fx_svc.FxUnavailableError):
        analytics_svc.bundle(conn, OWNER_ID, _conv(), today=WORLD_TODAY, period="month")


def test_transactions_of_a_soft_deleted_account_are_excluded_from_every_panel(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    owner = world_with_two_users.owner
    eur = accounts_repo.create(
        conn, OWNER_ID, NewAccount(name="eur", currency="EUR", opening_balance=0)
    ).id
    _txn(conn, OWNER_ID, on=WORLD_DAY, category_id=owner.category_id, account_id=eur, amount=100)
    accounts_repo.soft_delete(conn, OWNER_ID, eur)
    data = analytics_svc.bundle(
        conn, OWNER_ID, _conv(), today=WORLD_TODAY, period="month"
    )  # no EUR rate
    assert analytics_svc.spend_total_minor(data) == 1_000
    assert [i.amount_minor for i in data.largest_items] == [1_000]
    assert analytics_svc.twelve_month_avg_by_category(data) == {owner.category_id: 83}
    assert [m.expense_minor for m in data.income_vs_expense_monthly] == [1_000]


# --- helpers --------------------------------------------------------------------------------


def test_reference_today_keeps_today_for_the_current_month_only() -> None:
    today = date(2026, 11, 12)
    assert analytics_svc.reference_today(today, 2026, 11) == today
    assert analytics_svc.reference_today(today, 2026, 10) == date(2026, 10, 31)
    assert analytics_svc.reference_today(today, 2025, 11) == date(2025, 11, 30)
    assert analytics_svc.reference_today(today, 2026, 12) == date(2026, 12, 31)
    assert analytics_svc.reference_today(today, 2026, 2) == date(2026, 2, 28)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("month", "month"),
        ("year", "year"),
        ("trailing-12", "trailing-12"),
        ("YEAR", "month"),
        ("bogus", "month"),
        ("", "month"),
        (None, "month"),
    ],
)
def test_normalize_period(raw: str | None, expected: str) -> None:
    assert analytics_svc.normalize_period(raw) == expected


# --- soft-deleted / orphaned categories, future rows ---------------------------------------------


def test_soft_deleted_income_category_still_counts_in_monthly_flow(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    owner = world_with_two_users.owner
    old_income = _cat(conn, "old-income", Direction.INCOME)
    _txn(
        conn,
        OWNER_ID,
        on=WORLD_DAY,
        category_id=old_income,
        account_id=owner.account_id,
        amount=4_000,
    )
    categories_repo.soft_delete(conn, OWNER_ID, old_income)
    data = analytics_svc.bundle(conn, OWNER_ID, _conv(), today=WORLD_TODAY)
    assert [(m.income_minor, m.expense_minor) for m in data.income_vs_expense_monthly] == [
        (4_000, 1_000)
    ]
    # income categories never show up in the expense panels
    assert owner.income_category_id not in analytics_svc.twelve_month_avg_by_category(data)
    assert old_income not in analytics_svc.twelve_month_avg_by_category(data)


def test_largest_items_and_averages_exclude_income_and_future_rows(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    owner = world_with_two_users.owner
    _txn(
        conn,
        OWNER_ID,
        on=WORLD_DAY,
        category_id=owner.income_category_id,
        account_id=owner.account_id,
        amount=900_000,
    )
    _txn(
        conn,
        OWNER_ID,
        on=date(2027, 3, 1),
        category_id=owner.category_id,
        account_id=owner.account_id,
        amount=800_000,
    )
    data = analytics_svc.bundle(conn, OWNER_ID, _conv(), today=WORLD_TODAY, period="year")
    assert [i.amount_minor for i in data.largest_items] == [1_000]
    assert analytics_svc.twelve_month_avg_by_category(data) == {owner.category_id: 83}
    assert analytics_svc.spend_total_minor(data) == 1_000
    # the 2027 row lies after the trailing-12 window: the flow stays on November 2026
    assert [
        (m.year, m.month, m.income_minor, m.expense_minor) for m in data.income_vs_expense_monthly
    ] == [(2026, 11, 900_000, 1_000)]
