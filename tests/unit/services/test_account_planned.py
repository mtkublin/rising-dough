"""Accounts planned net per account (T-ACC1, ADR-0089)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.config import Settings
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction, OverrideState
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import (
    AmountFormula,
    FormulaTerm,
    NewRecurringOverride,
    NewRecurringRule,
)
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts,
    categories,
    planned,
    recurring,
    transactions,
)
from budget_planner.services import account_planned as svc, preferences
from budget_planner.services.recurring import PromotionEdits, promote_recurring

USER_ID = 1
TODAY = date(2026, 11, 6)
SETTINGS = Settings(_env_file=None, base_currency="PLN")


@pytest.fixture
def w(conn: sqlite3.Connection) -> dict[str, int]:
    a = accounts.create(
        conn, USER_ID, NewAccount(name="A", currency="PLN", opening_balance=100_000)
    )
    b = accounts.create(conn, USER_ID, NewAccount(name="B", currency="PLN", opening_balance=0))
    e = accounts.create(conn, USER_ID, NewAccount(name="E", currency="EUR", opening_balance=5_000))
    sal = categories.create(conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME))
    rent = categories.create(conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE))
    fun = categories.create(conn, USER_ID, NewCategory(name="Fun", direction=Direction.EXPENSE))
    bonus = categories.create(conn, USER_ID, NewCategory(name="Bonus", direction=Direction.INCOME))
    transit = categories.find_by_name(conn, USER_ID, "Transit")
    assert transit is not None
    return {
        "a": a.id,
        "b": b.id,
        "e": e.id,
        "sal": sal.id,
        "rent": rent.id,
        "fun": fun.id,
        "tr": transit.id,
        "bonus": bonus.id,
    }


def _anchor(
    conn: sqlite3.Connection, w: dict[str, int], *, landed: date, next_on: date | None
) -> None:
    preferences.set_income_anchor_category_id(conn, USER_ID, w["sal"])
    transactions.create(
        conn,
        USER_ID,
        NewTransaction(operation_date=landed, category_id=w["sal"], account_id=w["a"], amount=1),
    )
    if next_on is not None:
        _plan(conn, w, "sal", "a", 1, next_on)


def _plan(  # noqa: PLR0917
    conn: sqlite3.Connection,
    w: dict[str, int],
    cat: str,
    acct: str,
    amount: int,
    on: date,
    dest: str | None = None,
) -> int:
    return planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=on,
            category_id=w[cat],
            account_id=w[acct],
            dest_account_id=w[dest] if dest else None,
            amount=amount,
            description="x",
        ),
    ).id


def _rule(
    conn: sqlite3.Connection,
    w: dict[str, int],
    cat: str,
    amount: int,
    next_due: date,
    *,
    acct: str = "a",
    formula: AmountFormula | None = None,
) -> int:
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 7, next_due.day),
            category_id=w[cat],
            account_id=w[acct],
            default_amount=amount,
            day_of_month=next_due.day,
            amount_formula=formula,
        ),
    )
    recurring.set_next_due(conn, USER_ID, rule.id, next_due=next_due, last_promoted_date=None)
    return rule.id


def _nets(conn: sqlite3.Connection) -> dict[int, int]:
    res = svc.compute_accounts_planned(conn, USER_ID, TODAY, SETTINGS)
    return {k: v.net_minor for k, v in res.by_account.items() if v.net_minor}


def test_overdue_unpromoted_planned_counted(conn: sqlite3.Connection, w: dict[str, int]) -> None:
    _anchor(conn, w, landed=date(2026, 11, 2), next_on=date(2026, 11, 25))
    _plan(conn, w, "rent", "a", 700, date(2026, 11, 3))  # overdue, >= period_start
    _plan(conn, w, "rent", "a", 900, date(2026, 11, 1))  # before period_start
    # explicit: -700 (rent) + 1 (planned salary 11-25 is the window end, excluded)
    assert svc.planned_net_by_account(conn, USER_ID, svc.resolve_window(conn, USER_ID, TODAY)) == {
        w["a"]: -700
    }


def test_promoted_planned_excluded(conn: sqlite3.Connection, w: dict[str, int]) -> None:
    _anchor(conn, w, landed=date(2026, 11, 2), next_on=date(2026, 11, 25))
    pid = _plan(conn, w, "rent", "a", 700, date(2026, 11, 10))
    txn = transactions.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=TODAY,
            category_id=w["rent"],
            account_id=w["a"],
            amount=700,
            promoted_from_planned_id=pid,
        ),
    )
    planned.stamp_promotion(conn, USER_ID, pid, txn.id)
    assert _nets(conn) == {}


def test_recurring_early_promoted_not_counted(conn: sqlite3.Connection, w: dict[str, int]) -> None:
    _anchor(conn, w, landed=date(2026, 11, 2), next_on=date(2026, 11, 25))
    rid = _rule(conn, w, "rent", 500, date(2026, 11, 20))
    promote_recurring(conn, USER_ID, rid, PromotionEdits(operation_date=TODAY))
    assert _nets(conn) == {}


def test_recurring_overdue_unpromoted_counted(conn: sqlite3.Connection, w: dict[str, int]) -> None:
    _anchor(conn, w, landed=date(2026, 11, 2), next_on=date(2026, 11, 25))
    _rule(conn, w, "rent", 500, date(2026, 11, 3))
    assert _nets(conn) == {w["a"]: -500}


def test_recurring_before_period_start_ignored(conn: sqlite3.Connection, w: dict[str, int]) -> None:
    _anchor(conn, w, landed=date(2026, 11, 2), next_on=date(2026, 11, 25))
    _rule(conn, w, "rent", 500, date(2026, 10, 30))
    # Oct 30 occurrence is before period_start; next occurrence is Nov 30 (> end).
    assert _nets(conn) == {}


def test_recurring_formula_override_and_skip(conn: sqlite3.Connection, w: dict[str, int]) -> None:
    _anchor(conn, w, landed=date(2026, 11, 2), next_on=date(2026, 11, 25))
    src = categories.create(conn, USER_ID, NewCategory(name="Src", direction=Direction.EXPENSE))
    w = {**w, "src": src.id}
    _rule(conn, w, "src", 2000, date(2026, 11, 20))  # source, also counted: -2000
    formula = AmountFormula(
        terms=(FormulaTerm(sign="+", coefficient_bps=5000, source_category_ids=(src.id,)),)
    )
    _rule(conn, w, "fun", 1, date(2026, 11, 12), formula=formula)  # 50% of 2000 = -1000
    over = _rule(conn, w, "rent", 300, date(2026, 11, 14))
    recurring.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=over,
            occurrence_date=date(2026, 11, 14),
            state=OverrideState.OVERRIDDEN,
            amount_override=450,
        ),
    )
    skipped = _rule(conn, w, "rent", 9999, date(2026, 11, 16))
    recurring.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=skipped, occurrence_date=date(2026, 11, 16), state=OverrideState.SKIPPED
        ),
    )
    assert _nets(conn) == {w["a"]: -(2000 + 1000 + 450)}


def test_expense_income_transfer_legs(conn: sqlite3.Connection, w: dict[str, int]) -> None:
    _anchor(conn, w, landed=date(2026, 11, 2), next_on=date(2026, 11, 25))
    _plan(conn, w, "rent", "a", 300, date(2026, 11, 10))
    _plan(conn, w, "bonus", "b", 700, date(2026, 11, 12))
    _plan(conn, w, "tr", "a", 200, date(2026, 11, 15), dest="b")
    assert _nets(conn) == {w["a"]: -500, w["b"]: 900}
    res = svc.compute_accounts_planned(conn, USER_ID, TODAY, SETTINGS)
    assert res.by_account[w["a"]].projected_minor == 100_001 - 500


def test_unbudgeted_included(conn: sqlite3.Connection, w: dict[str, int]) -> None:
    _anchor(conn, w, landed=date(2026, 11, 2), next_on=date(2026, 11, 25))
    _plan(conn, w, "fun", "a", 123, date(2026, 11, 10))  # no budget defined
    assert _nets(conn) == {w["a"]: -123}


def test_window_falls_back_to_eom_without_anchor(
    conn: sqlite3.Connection, w: dict[str, int]
) -> None:
    window = svc.resolve_window(conn, USER_ID, TODAY)
    assert window == svc.PlannedWindow(start=date(2026, 11, 1), end=date(2026, 12, 1))
    _plan(conn, w, "rent", "a", 10, date(2026, 11, 30))
    _plan(conn, w, "rent", "a", 20, date(2026, 12, 1))
    assert _nets(conn) == {w["a"]: -10}


def test_window_eom_when_no_next_income(conn: sqlite3.Connection, w: dict[str, int]) -> None:
    _anchor(conn, w, landed=date(2026, 11, 2), next_on=None)
    window = svc.resolve_window(conn, USER_ID, TODAY)
    assert window == svc.PlannedWindow(start=date(2026, 11, 2), end=date(2026, 12, 1))


def test_not_eom_when_budget_total_zero_but_next_income(
    conn: sqlite3.Connection, w: dict[str, int]
) -> None:
    _anchor(conn, w, landed=date(2026, 11, 2), next_on=date(2026, 11, 25))  # no budgets at all
    window = svc.resolve_window(conn, USER_ID, TODAY)
    assert window.end == date(2026, 11, 25)
    _plan(conn, w, "rent", "a", 40, date(2026, 11, 28))  # after next income -> excluded
    assert _nets(conn) == {}


def test_currency_isolation_and_hero_base_only(conn: sqlite3.Connection, w: dict[str, int]) -> None:
    _anchor(conn, w, landed=date(2026, 11, 2), next_on=date(2026, 11, 25))
    _plan(conn, w, "rent", "a", 300, date(2026, 11, 10))
    _plan(conn, w, "rent", "e", 77, date(2026, 11, 10))
    res = svc.compute_accounts_planned(conn, USER_ID, TODAY, SETTINGS)
    assert res.by_account[w["e"]].net_minor == -77
    assert res.by_account[w["e"]].currency == "EUR"
    assert res.base_net_minor == -300


def test_adjustment_direction_ignored() -> None:
    from budget_planner.services.account_planned import _legs  # noqa: PLC0415

    assert _legs(Direction.ADJUSTMENT, 1, None, 5) == ()


def test_archived_category_items_still_counted(conn: sqlite3.Connection, w: dict[str, int]) -> None:
    _anchor(conn, w, landed=date(2026, 11, 2), next_on=date(2026, 11, 25))
    _plan(conn, w, "rent", "a", 300, date(2026, 11, 10))  # expense, unpromoted
    _plan(conn, w, "bonus", "b", 700, date(2026, 11, 12))  # income, unpromoted
    _rule(conn, w, "fun", 500, date(2026, 11, 14))  # expense, active rule
    for key in ("rent", "bonus", "fun"):
        categories.soft_delete(conn, USER_ID, w[key])
    # No KeyError; legs keep the sign of their (archived) category's direction.
    assert _nets(conn) == {w["a"]: -800, w["b"]: 700}


def test_recurring_date_override_uses_canonical_date_for_window(
    conn: sqlite3.Connection, w: dict[str, int]
) -> None:
    _anchor(conn, w, landed=date(2026, 11, 2), next_on=date(2026, 11, 25))
    # Canonical 11-20 is inside the window; override moves it past the end -> still counted.
    inside = _rule(conn, w, "rent", 400, date(2026, 11, 20))
    recurring.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=inside,
            occurrence_date=date(2026, 11, 20),
            state=OverrideState.OVERRIDDEN,
            date_override=date(2026, 12, 5),
        ),
    )
    # Canonical 11-27 is outside the window; override pulls it inside -> not counted.
    outside = _rule(conn, w, "fun", 900, date(2026, 11, 27))
    recurring.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=outside,
            occurrence_date=date(2026, 11, 27),
            state=OverrideState.OVERRIDDEN,
            date_override=date(2026, 11, 10),
        ),
    )
    assert _nets(conn) == {w["a"]: -400}
