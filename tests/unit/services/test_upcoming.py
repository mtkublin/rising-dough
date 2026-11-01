"""Tests for `services.upcoming.list_upcoming` (T-119, ADR-0038).

Each test uses ``update_rule(PatchRecurringRule(next_due=...))`` to pin
``rule.next_due`` into the test's logical ``today`` window because the
repository's ``_compute_initial_next_due`` reads *actual* ``date.today()``
when a rule is created — that would skip the rule past the test's logical
window on any real-world run date.
"""

from __future__ import annotations

import datetime as dt
import sqlite3

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction, OverrideState
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import (
    AmountFormula,
    FormulaTerm,
    NewRecurringOverride,
    NewRecurringRule,
    PatchRecurringRule,
    RecurringRule,
)
from budget_planner.repositories import accounts, categories, planned, recurring
from budget_planner.services import upcoming as upcoming_svc


@pytest.fixture
def ids(conn: sqlite3.Connection) -> dict[str, int]:
    checking = accounts.create(conn, NewAccount(name="Checking", currency="PLN")).id
    rent_cat = categories.create(conn, NewCategory(name="Rent", direction=Direction.EXPENSE)).id
    food_cat = categories.create(conn, NewCategory(name="Food", direction=Direction.EXPENSE)).id
    salary_cat = categories.create(conn, NewCategory(name="Salary", direction=Direction.INCOME)).id
    vat_cat = categories.create(conn, NewCategory(name="VAT", direction=Direction.EXPENSE)).id
    return {
        "checking": checking,
        "rent": rent_cat,
        "food": food_cat,
        "salary": salary_cat,
        "vat": vat_cat,
    }


def _rule_with_next_due(
    conn: sqlite3.Connection,
    *,
    start_date: dt.date,
    next_due: dt.date,
    category_id: int,
    account_id: int,
    amount: int = 200_000,
    description: str = "rent",
) -> RecurringRule:
    rule = recurring.create_rule(
        conn,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=start_date,
            category_id=category_id,
            account_id=account_id,
            default_amount=amount,
            default_description=description,
        ),
    )
    return recurring.update_rule(conn, rule.id, PatchRecurringRule(next_due=next_due))


# ---------------------------------------------------------------------------
# planned-only
# ---------------------------------------------------------------------------
def test_planned_only(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    today = dt.date(2026, 5, 10)
    planned.create(
        conn,
        NewPlannedTransaction(
            operation_date=dt.date(2026, 5, 15),
            category_id=ids["food"],
            account_id=ids["checking"],
            amount=5_000,
            description="groceries",
        ),
    )
    items = upcoming_svc.list_upcoming(conn, today=today, window_days=30)
    assert len(items) == 1
    item = items[0]
    assert item.kind == "planned"
    assert item.effective_date == dt.date(2026, 5, 15)
    assert item.description == "groceries"
    assert item.is_overdue is False
    assert item.rule_id is None
    assert item.planned_id is not None


def test_planned_overdue_flag(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    today = dt.date(2026, 5, 10)
    planned.create(
        conn,
        NewPlannedTransaction(
            operation_date=dt.date(2026, 5, 1),
            category_id=ids["food"],
            account_id=ids["checking"],
            amount=5_000,
            description="late bill",
        ),
    )
    items = upcoming_svc.list_upcoming(conn, today=today, window_days=30)
    assert len(items) == 1
    assert items[0].is_overdue is True


# ---------------------------------------------------------------------------
# recurring-only
# ---------------------------------------------------------------------------
def test_recurring_only(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    today = dt.date(2026, 5, 10)
    _rule_with_next_due(
        conn,
        start_date=dt.date(2026, 5, 20),
        next_due=dt.date(2026, 5, 20),
        category_id=ids["rent"],
        account_id=ids["checking"],
    )
    items = upcoming_svc.list_upcoming(conn, today=today, window_days=30)
    assert len(items) == 1
    item = items[0]
    assert item.kind == "recurring"
    assert item.effective_date == dt.date(2026, 5, 20)
    assert item.amount_minor == 200_000
    assert item.description == "rent"
    assert item.is_overdue is False
    assert item.rule_id is not None
    assert item.planned_id is None


# ---------------------------------------------------------------------------
# mixed planned + recurring, sorting
# ---------------------------------------------------------------------------
def test_mixed_sorted_by_effective_date(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    today = dt.date(2026, 5, 10)
    planned.create(
        conn,
        NewPlannedTransaction(
            operation_date=dt.date(2026, 5, 25),
            category_id=ids["food"],
            account_id=ids["checking"],
            amount=1_000,
            description="later planned",
        ),
    )
    _rule_with_next_due(
        conn,
        start_date=dt.date(2026, 5, 15),
        next_due=dt.date(2026, 5, 15),
        category_id=ids["rent"],
        account_id=ids["checking"],
    )
    items = upcoming_svc.list_upcoming(conn, today=today, window_days=30)
    assert len(items) == 2
    assert items[0].effective_date == dt.date(2026, 5, 15)
    assert items[0].kind == "recurring"
    assert items[1].effective_date == dt.date(2026, 5, 25)
    assert items[1].kind == "planned"


def test_tie_break_planned_first(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    today = dt.date(2026, 5, 10)
    planned.create(
        conn,
        NewPlannedTransaction(
            operation_date=dt.date(2026, 5, 15),
            category_id=ids["food"],
            account_id=ids["checking"],
            amount=1_000,
            description="planned same day",
        ),
    )
    _rule_with_next_due(
        conn,
        start_date=dt.date(2026, 5, 15),
        next_due=dt.date(2026, 5, 15),
        category_id=ids["rent"],
        account_id=ids["checking"],
        description="rent same day",
    )
    items = upcoming_svc.list_upcoming(conn, today=today, window_days=30)
    assert len(items) == 2
    assert items[0].kind == "planned"
    assert items[1].kind == "recurring"


# ---------------------------------------------------------------------------
# overrides on next_due
# ---------------------------------------------------------------------------
def test_override_merge_amount_and_description(
    conn: sqlite3.Connection, ids: dict[str, int]
) -> None:
    today = dt.date(2026, 5, 10)
    rule = _rule_with_next_due(
        conn,
        start_date=dt.date(2026, 5, 20),
        next_due=dt.date(2026, 5, 20),
        category_id=ids["rent"],
        account_id=ids["checking"],
    )
    recurring.upsert_override(
        conn,
        NewRecurringOverride(
            rule_id=rule.id,
            occurrence_date=dt.date(2026, 5, 20),
            state=OverrideState.OVERRIDDEN,
            amount_override=250_000,
            description_override="rent + fee",
        ),
    )
    items = upcoming_svc.list_upcoming(conn, today=today, window_days=30)
    assert len(items) == 1
    assert items[0].amount_minor == 250_000
    assert items[0].description == "rent + fee"
    assert items[0].override_present is True
    assert items[0].effective_date == dt.date(2026, 5, 20)


def test_override_date_shift_still_inside_window(
    conn: sqlite3.Connection, ids: dict[str, int]
) -> None:
    today = dt.date(2026, 5, 10)
    rule = _rule_with_next_due(
        conn,
        start_date=dt.date(2026, 5, 20),
        next_due=dt.date(2026, 5, 20),
        category_id=ids["rent"],
        account_id=ids["checking"],
    )
    recurring.upsert_override(
        conn,
        NewRecurringOverride(
            rule_id=rule.id,
            occurrence_date=dt.date(2026, 5, 20),
            state=OverrideState.OVERRIDDEN,
            date_override=dt.date(2026, 5, 25),
        ),
    )
    items = upcoming_svc.list_upcoming(conn, today=today, window_days=30)
    assert len(items) == 1
    assert items[0].effective_date == dt.date(2026, 5, 25)


def test_override_moves_date_outside_window_excluded(
    conn: sqlite3.Connection, ids: dict[str, int]
) -> None:
    today = dt.date(2026, 5, 10)
    rule = _rule_with_next_due(
        conn,
        start_date=dt.date(2026, 5, 20),
        next_due=dt.date(2026, 5, 20),
        category_id=ids["rent"],
        account_id=ids["checking"],
    )
    recurring.upsert_override(
        conn,
        NewRecurringOverride(
            rule_id=rule.id,
            occurrence_date=dt.date(2026, 5, 20),
            state=OverrideState.OVERRIDDEN,
            date_override=dt.date(2026, 7, 15),  # beyond 30-day window.
        ),
    )
    items = upcoming_svc.list_upcoming(conn, today=today, window_days=30)
    assert items == ()


def test_skipped_override_excluded(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    today = dt.date(2026, 5, 10)
    rule = _rule_with_next_due(
        conn,
        start_date=dt.date(2026, 5, 20),
        next_due=dt.date(2026, 5, 20),
        category_id=ids["rent"],
        account_id=ids["checking"],
    )
    recurring.upsert_override(
        conn,
        NewRecurringOverride(
            rule_id=rule.id,
            occurrence_date=dt.date(2026, 5, 20),
            state=OverrideState.SKIPPED,
        ),
    )
    items = upcoming_svc.list_upcoming(conn, today=today, window_days=30)
    assert items == ()


# ---------------------------------------------------------------------------
# window_days=None → unbounded forward
# ---------------------------------------------------------------------------
def test_window_days_none_returns_all(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    today = dt.date(2026, 5, 10)
    planned.create(
        conn,
        NewPlannedTransaction(
            operation_date=dt.date(2026, 12, 25),
            category_id=ids["food"],
            account_id=ids["checking"],
            amount=1_000,
            description="far-off planned",
        ),
    )
    _rule_with_next_due(
        conn,
        start_date=dt.date(2027, 1, 1),
        next_due=dt.date(2027, 1, 1),
        category_id=ids["rent"],
        account_id=ids["checking"],
        amount=1_000_000,
        description="yearly fee",
    )
    items = upcoming_svc.list_upcoming(conn, today=today, window_days=None)
    assert len(items) == 2
    assert {i.kind for i in items} == {"planned", "recurring"}


def test_window_days_narrow_filters_recurring(
    conn: sqlite3.Connection, ids: dict[str, int]
) -> None:
    today = dt.date(2026, 5, 10)
    _rule_with_next_due(
        conn,
        start_date=dt.date(2026, 6, 20),  # outside 7-day window.
        next_due=dt.date(2026, 6, 20),
        category_id=ids["rent"],
        account_id=ids["checking"],
    )
    items = upcoming_svc.list_upcoming(conn, today=today, window_days=7)
    assert items == ()


# ---------------------------------------------------------------------------
# promoted + inactive excluded
# ---------------------------------------------------------------------------
def test_inactive_rule_excluded(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    today = dt.date(2026, 5, 10)
    rule = _rule_with_next_due(
        conn,
        start_date=dt.date(2026, 5, 20),
        next_due=dt.date(2026, 5, 20),
        category_id=ids["rent"],
        account_id=ids["checking"],
    )
    recurring.deactivate_rule(conn, rule.id)
    items = upcoming_svc.list_upcoming(conn, today=today, window_days=30)
    assert items == ()


# ---------------------------------------------------------------------------
# ADR-0063 — stop-date filter
# ---------------------------------------------------------------------------
def test_active_rule_past_end_date_excluded(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    """Active rule whose next_due > end_date must not surface pre-promotion."""
    today = dt.date(2026, 5, 10)
    rule = _rule_with_next_due(
        conn,
        start_date=dt.date(2026, 1, 20),
        next_due=dt.date(2026, 5, 20),
        category_id=ids["rent"],
        account_id=ids["checking"],
    )
    # Pin end_date before next_due so the rule should be filtered.
    recurring.update_rule(conn, rule.id, PatchRecurringRule(end_date=dt.date(2026, 4, 20)))
    items = upcoming_svc.list_upcoming(conn, today=today, window_days=90)
    assert items == ()


def test_active_rule_at_end_date_included(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    """end_date == next_due keeps the final occurrence in Upcoming (inclusive)."""
    today = dt.date(2026, 5, 10)
    rule = _rule_with_next_due(
        conn,
        start_date=dt.date(2026, 1, 20),
        next_due=dt.date(2026, 5, 20),
        category_id=ids["rent"],
        account_id=ids["checking"],
    )
    recurring.update_rule(conn, rule.id, PatchRecurringRule(end_date=dt.date(2026, 5, 20)))
    items = upcoming_svc.list_upcoming(conn, today=today, window_days=30)
    assert len(items) == 1
    assert items[0].effective_date == dt.date(2026, 5, 20)


# ---------------------------------------------------------------------------
# formula-derived recurring amount (ADR-0047) — surfaces on Today Upcoming
# ---------------------------------------------------------------------------
def test_recurring_formula_amount_resolved(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    """Formula rule's upcoming row reflects the computed value, not default_amount."""
    today = dt.date(2026, 5, 10)
    _rule_with_next_due(
        conn,
        start_date=dt.date(2026, 5, 20),
        next_due=dt.date(2026, 5, 20),
        category_id=ids["salary"],
        account_id=ids["checking"],
        amount=10_000_00,
        description="salary",
    )
    formula = AmountFormula(
        terms=(FormulaTerm(sign="+", coefficient_bps=2300, source_category_ids=(ids["salary"],)),)
    )
    vat_rule = recurring.create_rule(
        conn,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=dt.date(2026, 5, 20),
            category_id=ids["vat"],
            account_id=ids["checking"],
            default_amount=0,
            default_description="salary VAT",
            amount_formula=formula,
        ),
    )
    vat_rule = recurring.update_rule(
        conn, vat_rule.id, PatchRecurringRule(next_due=dt.date(2026, 5, 20))
    )
    items = upcoming_svc.list_upcoming(conn, today=today, window_days=30)
    vat_item = next(i for i in items if i.rule_id == vat_rule.id)
    assert vat_item.amount_minor == 230_000  # 23% of 10_000.00 = 2_300.00
    assert vat_item.is_formula is True
    assert vat_item.override_present is False


def test_recurring_non_formula_has_is_formula_false(
    conn: sqlite3.Connection, ids: dict[str, int]
) -> None:
    today = dt.date(2026, 5, 10)
    _rule_with_next_due(
        conn,
        start_date=dt.date(2026, 5, 20),
        next_due=dt.date(2026, 5, 20),
        category_id=ids["rent"],
        account_id=ids["checking"],
    )
    (item,) = upcoming_svc.list_upcoming(conn, today=today, window_days=30)
    assert item.is_formula is False


def test_planned_is_formula_false(conn: sqlite3.Connection, ids: dict[str, int]) -> None:
    today = dt.date(2026, 5, 10)
    planned.create(
        conn,
        NewPlannedTransaction(
            operation_date=dt.date(2026, 5, 15),
            category_id=ids["food"],
            account_id=ids["checking"],
            amount=5_000,
            description="groceries",
        ),
    )
    (item,) = upcoming_svc.list_upcoming(conn, today=today, window_days=30)
    assert item.is_formula is False


def test_formula_rule_with_amount_override_prefers_override(
    conn: sqlite3.Connection, ids: dict[str, int]
) -> None:
    """Override on next_due still wins over the formula result (ADR-0038 precedence)."""
    today = dt.date(2026, 5, 10)
    _rule_with_next_due(
        conn,
        start_date=dt.date(2026, 5, 20),
        next_due=dt.date(2026, 5, 20),
        category_id=ids["salary"],
        account_id=ids["checking"],
        amount=10_000_00,
        description="salary",
    )
    formula = AmountFormula(
        terms=(FormulaTerm(sign="+", coefficient_bps=2300, source_category_ids=(ids["salary"],)),)
    )
    vat_rule = recurring.create_rule(
        conn,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=dt.date(2026, 5, 20),
            category_id=ids["vat"],
            account_id=ids["checking"],
            default_amount=0,
            default_description="salary VAT",
            amount_formula=formula,
        ),
    )
    vat_rule = recurring.update_rule(
        conn, vat_rule.id, PatchRecurringRule(next_due=dt.date(2026, 5, 20))
    )
    recurring.upsert_override(
        conn,
        NewRecurringOverride(
            rule_id=vat_rule.id,
            occurrence_date=dt.date(2026, 5, 20),
            state=OverrideState.OVERRIDDEN,
            amount_override=999_00,
        ),
    )
    items = upcoming_svc.list_upcoming(conn, today=today, window_days=30)
    vat_item = next(i for i in items if i.rule_id == vat_rule.id)
    assert vat_item.amount_minor == 999_00
    assert vat_item.is_formula is True
    assert vat_item.override_present is True
