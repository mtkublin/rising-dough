"""Tests for the budget service (T-024 / T-120)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner import clock
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import (
    NewBudgetDefault,
    NewBudgetOneOffOverride,
    NewBudgetRecurringOverride,
)
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction, OverrideState
from budget_planner.domain.planned import NewPlannedTransaction, PlannedFilter
from budget_planner.domain.preferences import PREF_INCOME_ANCHOR_CATEGORY_ID
from budget_planner.domain.recurring import (
    NewRecurringOverride,
    NewRecurringRule,
    PatchRecurringRule,
)
from budget_planner.domain.transactions import NewTransaction, TransactionFilter
from budget_planner.repositories import (
    accounts,
    budgets,
    categories,
    planned,
    preferences as preferences_repo,
    recurring,
    transactions,
)
from budget_planner.services import (
    budget as bs,
    planned as planned_svc,
    recurring as recurring_svc,
)
from tests.formula_fx_support import formula_fx_of

USER_ID = 1


@pytest.fixture
def seed(conn: sqlite3.Connection) -> dict[str, int]:
    checking = accounts.create(
        conn, USER_ID, NewAccount(name="Checking", currency="PLN", opening_balance=0)
    ).id
    groceries = categories.create(
        conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    ).id
    rent = categories.create(
        conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    ).id
    utilities = categories.create(
        conn, USER_ID, NewCategory(name="Utilities", direction=Direction.EXPENSE)
    ).id
    gym = categories.create(conn, USER_ID, NewCategory(name="Gym", direction=Direction.EXPENSE)).id
    salary = categories.create(
        conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    ).id

    budgets.set_default(conn, USER_ID, NewBudgetDefault(category_id=groceries, amount=120_000))
    budgets.set_default(conn, USER_ID, NewBudgetDefault(category_id=rent, amount=300_000))
    budgets.set_default(conn, USER_ID, NewBudgetDefault(category_id=utilities, amount=40_000))

    budgets.set_recurring(
        conn, USER_ID, NewBudgetRecurringOverride(category_id=rent, month=1, amount=310_000)
    )
    budgets.set_one_off(
        conn,
        USER_ID,
        NewBudgetOneOffOverride(category_id=utilities, year=2026, month=2, amount=60_000),
    )

    def _txn(d: date, cat: int, amount: int) -> int:
        return transactions.create(
            conn,
            USER_ID,
            NewTransaction(operation_date=d, category_id=cat, account_id=checking, amount=amount),
        ).id

    _txn(date(2026, 1, 5), groceries, 30_000)
    _txn(date(2026, 1, 20), groceries, 40_000)
    _txn(date(2026, 1, 25), rent, 310_000)
    _txn(date(2026, 2, 2), utilities, 55_000)
    _txn(date(2026, 2, 10), groceries, 45_000)
    _txn(date(2025, 11, 15), groceries, 35_000)
    # Income + adjustment: must not touch spent/averages.
    _txn(date(2026, 1, 25), salary, 500_000)

    return {
        "checking": checking,
        "groceries": groceries,
        "rent": rent,
        "utilities": utilities,
        "gym": gym,
        "salary": salary,
    }


# ---------------------------------------------------------------------------
# resolve_budget
# ---------------------------------------------------------------------------
def test_default_only(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    assert bs.resolve_budget(conn, USER_ID, seed["groceries"], 2026, 3) == 120_000


def test_recurring_beats_default(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    assert bs.resolve_budget(conn, USER_ID, seed["rent"], 2026, 1) == 310_000


def test_recurring_only_in_its_month(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    assert bs.resolve_budget(conn, USER_ID, seed["rent"], 2026, 7) == 300_000


def test_one_off_beats_both(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    assert bs.resolve_budget(conn, USER_ID, seed["utilities"], 2026, 2) == 60_000


def test_one_off_single_year(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    assert bs.resolve_budget(conn, USER_ID, seed["utilities"], 2027, 2) == 40_000


def test_unbudgeted_returns_none(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    assert bs.resolve_budget(conn, USER_ID, seed["gym"], 2026, 3) is None


def test_zero_default_returns_zero(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    budgets.set_default(conn, USER_ID, NewBudgetDefault(category_id=seed["gym"], amount=0))
    assert bs.resolve_budget(conn, USER_ID, seed["gym"], 2026, 4) == 0


# ---------------------------------------------------------------------------
# month_summary
# ---------------------------------------------------------------------------
def test_january_summary(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    # today=Jan 31 so the paycheck window captures every January expense;
    # fixture does not bind an income anchor, so period_start = month start
    # per ADR-0041 fallback.
    s = bs.month_summary(conn, USER_ID, 2026, 1, today=date(2026, 1, 31), base_currency="PLN")
    assert s.year == 2026
    assert s.month == 1
    by_cat = {line.category_id: line for line in s.lines}
    # Rent: recurring override 310_000; spent 310_000 → remaining 0.
    assert by_cat[seed["rent"]].budgeted_minor == 310_000
    assert by_cat[seed["rent"]].spent_minor == 310_000
    assert by_cat[seed["rent"]].remaining_minor == 0
    # Groceries: default 120_000; spent 70_000; remaining 50_000.
    assert by_cat[seed["groceries"]].budgeted_minor == 120_000
    assert by_cat[seed["groceries"]].spent_minor == 70_000
    assert by_cat[seed["groceries"]].remaining_minor == 50_000
    # Utilities: default 40_000, spent 0 → remaining 40_000.
    assert by_cat[seed["utilities"]].budgeted_minor == 40_000
    assert by_cat[seed["utilities"]].spent_minor == 0
    # Gym: unbudgeted, no spend.
    assert by_cat[seed["gym"]].budgeted_minor is None
    assert by_cat[seed["gym"]].remaining_minor is None


def test_february_delta_vs_prev_month(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    s = bs.month_summary(conn, USER_ID, 2026, 2, today=date(2026, 2, 15), base_currency="PLN")
    by_cat = {line.category_id: line for line in s.lines}
    # Utilities one-off 60_000; spent 55_000; remaining 5_000.
    assert by_cat[seed["utilities"]].budgeted_minor == 60_000
    assert by_cat[seed["utilities"]].spent_minor == 55_000
    assert by_cat[seed["utilities"]].remaining_minor == 5000
    # Groceries delta vs Jan: 45_000 - 70_000 = -25_000.
    assert by_cat[seed["groceries"]].delta_vs_prev_month_minor == -25_000


def test_totals_exclude_unbudgeted(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    s = bs.month_summary(conn, USER_ID, 2026, 1, today=date(2026, 1, 31), base_currency="PLN")
    # Budgeted: Rent 310k + Groceries 120k + Utilities 40k = 470k.
    assert s.totals.budgeted_minor == 470_000
    assert s.totals.spent_minor == 310_000 + 70_000 + 0
    assert s.totals.remaining_minor == 470_000 - (310_000 + 70_000)


def test_previous_month_rollover_january_to_december(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    s = bs.month_summary(conn, USER_ID, 2026, 1, today=date(2026, 1, 31), base_currency="PLN")
    by_cat = {line.category_id: line for line in s.lines}
    # No Dec 2025 Groceries in fixture → delta = 70_000.
    assert by_cat[seed["groceries"]].delta_vs_prev_month_minor == 70_000


def test_avg_monthly_overall_uses_active_months(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    s = bs.month_summary(conn, USER_ID, 2026, 2, today=date(2026, 2, 15), base_currency="PLN")
    by_cat = {line.category_id: line for line in s.lines}
    # Groceries active months: Nov 2025, Jan 2026, Feb 2026 → 3 months.
    # Sum = 35_000 + 70_000 + 45_000 = 150_000; avg = 50_000.
    assert by_cat[seed["groceries"]].avg_monthly_overall_minor == 50_000


def test_avg_this_year(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    s = bs.month_summary(conn, USER_ID, 2026, 2, today=date(2026, 2, 15), base_currency="PLN")
    by_cat = {line.category_id: line for line in s.lines}
    # Groceries YTD through Feb: Jan 70_000 + Feb 45_000 = 115_000; / 2 = 57_500.
    assert by_cat[seed["groceries"]].avg_this_year_minor == 57_500


def test_soft_deleted_excluded(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    # Delete a January Groceries txn → spent + averages drop.
    cat_id = seed["groceries"]
    jan_txns = transactions.list_filtered(
        conn,
        USER_ID,
        TransactionFilter(
            date_from=date(2026, 1, 1), date_to=date(2026, 1, 31), category_ids=(cat_id,)
        ),
    )
    assert jan_txns
    transactions.soft_delete(conn, USER_ID, jan_txns[0].id)
    s = bs.month_summary(conn, USER_ID, 2026, 1, today=date(2026, 1, 31), base_currency="PLN")
    by_cat = {line.category_id: line for line in s.lines}
    assert by_cat[cat_id].spent_minor == 70_000 - jan_txns[0].amount


def test_income_excluded_from_spent(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    s = bs.month_summary(conn, USER_ID, 2026, 1, today=date(2026, 1, 15), base_currency="PLN")
    by_cat = {line.category_id: line for line in s.lines}
    # Salary category is income — should not appear in month_summary lines.
    assert seed["salary"] not in by_cat


def test_adjustment_excluded(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    adj_cat = categories.find_by_name(conn, USER_ID, "Reconciliation")
    assert adj_cat is not None
    transactions.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 1, 10),
            category_id=adj_cat.id,
            account_id=seed["checking"],
            amount=-5000,
        ),
    )
    s = bs.month_summary(conn, USER_ID, 2026, 1, today=date(2026, 1, 31), base_currency="PLN")
    # Adjustment direction excluded; Groceries spent unchanged at 70_000.
    by_cat = {line.category_id: line for line in s.lines}
    assert by_cat[seed["groceries"]].spent_minor == 70_000


def test_sort_order_budgeted_first_then_alpha(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    s = bs.month_summary(conn, USER_ID, 2026, 1, today=date(2026, 1, 15), base_currency="PLN")
    # Budgeted lines first, then None-budget lines, each alpha by name.
    kinds = [line.budgeted_minor is None for line in s.lines]
    assert kinds == sorted(kinds)
    # Within budgeted group, names sorted.
    budgeted_names = [line.category_name for line in s.lines if line.budgeted_minor is not None]
    assert budgeted_names == sorted(budgeted_names)


# ---------------------------------------------------------------------------
# T-120 — committed_in_window + MonthTotals.committed_minor
# ---------------------------------------------------------------------------
def test_committed_defaults_to_zero_without_recurring_or_planned(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    """Phase 9 budget fixtures have no planned/recurring rows → committed=0."""
    s = bs.month_summary(conn, USER_ID, 2026, 1, today=date(2026, 1, 31), base_currency="PLN")
    assert s.totals.committed_minor == 0
    # Regression: remaining is still budgeted - spent when committed is zero.
    assert s.totals.remaining_minor == 470_000 - (310_000 + 70_000)


@pytest.fixture
def committed_world(conn: sqlite3.Connection) -> dict[str, int]:
    """A minimal expense + anchor world for exercising committed logic."""
    checking = accounts.create(
        conn, USER_ID, NewAccount(name="Checking", currency="PLN", opening_balance=0)
    ).id
    groceries = categories.create(
        conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    ).id
    rent = categories.create(
        conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    ).id
    salary = categories.create(
        conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    ).id
    # Baseline budgets so budgeted_total != 0 (otherwise committed is forced to 0).
    budgets.set_default(conn, USER_ID, NewBudgetDefault(category_id=groceries, amount=100_000))
    budgets.set_default(conn, USER_ID, NewBudgetDefault(category_id=rent, amount=300_000))
    return {
        "checking": checking,
        "groceries": groceries,
        "rent": rent,
        "salary": salary,
    }


def test_committed_in_window_planned_only(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 2, 10),
            category_id=committed_world["groceries"],
            account_id=committed_world["checking"],
            amount=12_000,
            description="Market",
        ),
    )
    # Unpromoted planned expense inside [Feb 1, Feb 15).
    total = bs.committed_in_window(
        conn,
        USER_ID,
        start=date(2026, 2, 1),
        end=date(2026, 2, 15),
        today=clock.utc_now().date(),
        base_currency="PLN",
    )
    assert total == 12_000
    # Promoted-row counterpart must NOT be counted.
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 2, 12),
            category_id=committed_world["groceries"],
            account_id=committed_world["checking"],
            amount=99_000,
        ),
    )
    # Flip the second row to promoted — it has to be excluded.
    rows = planned.list_filtered(
        conn,
        USER_ID,
        PlannedFilter(promoted=False, category_ids=(committed_world["groceries"],)),
    )
    assert rows
    # Reuse the real stamp-promotion path so repo invariants fire.
    txn = transactions.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 2, 12),
            category_id=committed_world["groceries"],
            account_id=committed_world["checking"],
            amount=99_000,
        ),
    )
    planned.stamp_promotion(conn, USER_ID, rows[-1].id, txn.id)
    total_after = bs.committed_in_window(
        conn,
        USER_ID,
        start=date(2026, 2, 1),
        end=date(2026, 2, 15),
        today=clock.utc_now().date(),
        base_currency="PLN",
    )
    # Only the first (unpromoted) planned row survives.
    assert total_after == 12_000


def test_committed_in_window_recurring_monthly_inside_window(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 2, 5),
            category_id=committed_world["rent"],
            account_id=committed_world["checking"],
            default_amount=300_000,
            default_description="Rent",
        ),
    )
    # Pin next_due into the test window.
    recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=date(2026, 2, 5)))
    total = bs.committed_in_window(
        conn,
        USER_ID,
        start=date(2026, 2, 1),
        end=date(2026, 2, 28),
        today=clock.utc_now().date(),
        base_currency="PLN",
    )
    assert total == 300_000


def test_committed_in_window_recurring_end_date_cuts_mid_window(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    """A recurring rule whose end_date falls inside the window excludes
    occurrences after end_date."""
    recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 2, 5),
            end_date=date(2026, 2, 20),
            category_id=committed_world["rent"],
            account_id=committed_world["checking"],
            default_amount=300_000,
            default_description="Rent",
        ),
    )
    # end_date = Feb 20; window extends to Mar 10 — the single Feb occurrence
    # is in; the hypothetical Mar occurrence is cut by end_date.
    total = bs.committed_in_window(
        conn,
        USER_ID,
        start=date(2026, 2, 1),
        end=date(2026, 3, 10),
        today=clock.utc_now().date(),
        base_currency="PLN",
    )
    assert total == 300_000


def test_committed_in_window_override_adjusts_amount(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 2, 5),
            category_id=committed_world["rent"],
            account_id=committed_world["checking"],
            default_amount=300_000,
            default_description="Rent",
        ),
    )
    recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=date(2026, 2, 5)))
    recurring.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=rule.id,
            occurrence_date=date(2026, 2, 5),
            state=OverrideState.OVERRIDDEN,
            amount_override=250_000,
        ),
    )
    total = bs.committed_in_window(
        conn,
        USER_ID,
        start=date(2026, 2, 1),
        end=date(2026, 2, 28),
        today=clock.utc_now().date(),
        base_currency="PLN",
    )
    assert total == 250_000


def test_committed_in_window_skipped_override_excluded(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 2, 5),
            category_id=committed_world["rent"],
            account_id=committed_world["checking"],
            default_amount=300_000,
        ),
    )
    recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=date(2026, 2, 5)))
    recurring.upsert_override(
        conn,
        USER_ID,
        NewRecurringOverride(
            rule_id=rule.id,
            occurrence_date=date(2026, 2, 5),
            state=OverrideState.SKIPPED,
        ),
    )
    total = bs.committed_in_window(
        conn,
        USER_ID,
        start=date(2026, 2, 1),
        end=date(2026, 2, 28),
        today=clock.utc_now().date(),
        base_currency="PLN",
    )
    assert total == 0


def test_committed_in_window_excludes_non_expense_directions(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    """Income + transit + adjustment recurring/planned must not be counted."""
    # Planned income row — must be excluded.
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 2, 10),
            category_id=committed_world["salary"],
            account_id=committed_world["checking"],
            amount=500_000,
        ),
    )
    # Recurring income rule — must be excluded.
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 2, 1),
            category_id=committed_world["salary"],
            account_id=committed_world["checking"],
            default_amount=500_000,
        ),
    )
    recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=date(2026, 2, 1)))
    total = bs.committed_in_window(
        conn,
        USER_ID,
        start=date(2026, 2, 1),
        end=date(2026, 2, 28),
        today=clock.utc_now().date(),
        base_currency="PLN",
    )
    assert total == 0


def test_committed_in_window_empty_range_short_circuits(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    total = bs.committed_in_window(
        conn,
        USER_ID,
        start=date(2026, 2, 15),
        end=date(2026, 2, 15),
        today=clock.utc_now().date(),
        base_currency="PLN",
    )
    assert total == 0


def test_month_summary_recurring_reduces_remaining_and_daily_spend(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    """One recurring expense due inside window shaves remaining + daily spend."""
    preferences_repo.upsert(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID, str(committed_world["salary"]))
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 2, 25),
            category_id=committed_world["salary"],
            account_id=committed_world["checking"],
            amount=500_000,
        ),
    )
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 2, 20),
            category_id=committed_world["rent"],
            account_id=committed_world["checking"],
            default_amount=300_000,
        ),
    )
    recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=date(2026, 2, 20)))

    s = bs.month_summary(conn, USER_ID, 2026, 2, today=date(2026, 2, 15), base_currency="PLN")
    # Window = [Feb 15, Feb 25). Recurring Feb 20 is in; rent 300_000.
    assert s.totals.committed_minor == 300_000
    # Baseline budgeted = 100k + 300k = 400k; spent_this_month = 0.
    assert s.totals.budgeted_minor == 400_000
    assert s.totals.spent_minor == 0
    assert s.totals.remaining_minor == 400_000 - 300_000
    assert s.days_until_next_income == 10
    # 100_000 / 10 = 10_000 banker's-round.
    assert s.left_daily_spend_minor == 10_000


def test_month_summary_promote_moves_committed_into_spent_zero_net(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    """Promoting a recurring row flips committed → spent; remaining unchanged.

    ADR-0041 shifts per-category spent to ``[last_anchor_date, today]`` and the
    promoted transaction only counts as spent when its ``operation_date`` is
    on-or-before ``today``. We pin today=Feb 20 so the committed Feb 20 rent
    is simultaneously inside ``[today, next_income_date)`` (committed) AND
    becomes a Feb-20 actual whose ``operation_date == today`` (spent) after
    promote — the zero-net invariant then holds.
    """
    preferences_repo.upsert(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID, str(committed_world["salary"]))
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 2, 25),
            category_id=committed_world["salary"],
            account_id=committed_world["checking"],
            amount=500_000,
        ),
    )
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 2, 20),
            category_id=committed_world["rent"],
            account_id=committed_world["checking"],
            default_amount=300_000,
        ),
    )
    recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=date(2026, 2, 20)))

    before = bs.month_summary(conn, USER_ID, 2026, 2, today=date(2026, 2, 20), base_currency="PLN")
    recurring_svc.promote_recurring(
        conn, USER_ID, rule.id, recurring_svc.PromotionEdits(), fx=formula_fx_of(conn, USER_ID)
    )
    after = bs.month_summary(conn, USER_ID, 2026, 2, today=date(2026, 2, 20), base_currency="PLN")

    # Committed drops by the promoted amount; spent rises by the same.
    assert after.totals.committed_minor == before.totals.committed_minor - 300_000
    assert after.totals.spent_minor == before.totals.spent_minor + 300_000
    # Net effect on remaining is zero (budgeted - spent - committed invariant).
    assert after.totals.remaining_minor == before.totals.remaining_minor


# ---------------------------------------------------------------------------
# T-125 (ADR-0041) — Paycheck-window spent: [last_anchor_date, today]
# ---------------------------------------------------------------------------
def _bind_anchor(conn: sqlite3.Connection, category_id: int) -> None:
    preferences_repo.upsert(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID, str(category_id))


def test_anchor_window_shifts_spent_to_post_anchor_only(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    """A promoted salary mid-month moves spent_minor to [salary_date, today]."""
    _bind_anchor(conn, seed["salary"])
    # Pin a second salary promotion later than Jan 25 so the window starts
    # Jan 25 for a today=Jan 30 call. The seed already has Jan 25 salary.
    # Groceries fixture: Jan 5 (30_000), Jan 20 (40_000), both BEFORE Jan 25.
    # Rent fixture: Jan 25 (310_000) — same day as anchor; inclusive window
    # keeps it in.
    s = bs.month_summary(conn, USER_ID, 2026, 1, today=date(2026, 1, 30), base_currency="PLN")
    by_cat = {line.category_id: line for line in s.lines}
    # Pre-anchor Groceries expenses (Jan 5 + Jan 20) are excluded.
    assert by_cat[seed["groceries"]].spent_minor == 0
    # Rent Jan 25 == anchor date — inclusive lower bound keeps it.
    assert by_cat[seed["rent"]].spent_minor == 310_000
    # Totals follow per-line sums.
    assert s.totals.spent_minor == 310_000
    # budgeted stays monthly; remaining uses the shifted spent.
    assert by_cat[seed["groceries"]].budgeted_minor == 120_000
    assert by_cat[seed["groceries"]].remaining_minor == 120_000  # 120_000 - 0


def test_no_prior_anchor_falls_back_to_month_start(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    """When no anchor-income txn <= today exists, use month start."""
    # Bind anchor, but delete all salary rows — no promoted anchor remains.
    _bind_anchor(conn, seed["salary"])
    salary_rows = transactions.list_filtered(
        conn, USER_ID, TransactionFilter(category_ids=(seed["salary"],))
    )
    for row in salary_rows:
        transactions.soft_delete(conn, USER_ID, row.id)

    # today=Jan 30 so the paycheck window would have shifted if a salary
    # existed. With no prior anchor row, fallback to month-start → the full
    # Groceries + Rent expenses up to today are summed.
    s = bs.month_summary(conn, USER_ID, 2026, 1, today=date(2026, 1, 30), base_currency="PLN")
    by_cat = {line.category_id: line for line in s.lines}
    # Month-start window [Jan 1, Jan 30] catches all January expenses.
    assert by_cat[seed["groceries"]].spent_minor == 70_000
    assert by_cat[seed["rent"]].spent_minor == 310_000


def test_zero_budget_month_unchanged(conn: sqlite3.Connection) -> None:
    """Zero-budget months keep month-start fallback (no anchor side effects)."""
    checking = accounts.create(
        conn, USER_ID, NewAccount(name="Checking", currency="PLN", opening_balance=0)
    ).id
    groceries = categories.create(
        conn, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    ).id
    salary = categories.create(
        conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    ).id
    # No budgets. Anchor bound + salary posted mid-month.
    _bind_anchor(conn, salary)
    transactions.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 1, 10),
            category_id=salary,
            account_id=checking,
            amount=500_000,
        ),
    )
    transactions.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 1, 5),
            category_id=groceries,
            account_id=checking,
            amount=20_000,
        ),
    )
    s = bs.month_summary(conn, USER_ID, 2026, 1, today=date(2026, 1, 20), base_currency="PLN")
    # budgeted_total == 0 → zero-budget branch; spent uses month-start window
    # (same as the pre-ADR-0041 behavior) so the per-line Groceries spent
    # keeps the Jan 5 txn.
    by_cat = {line.category_id: line for line in s.lines}
    assert s.totals.budgeted_minor == 0
    assert by_cat[groceries].spent_minor == 20_000
    assert s.left_daily_spend_minor is None


def test_no_anchor_configured_falls_back_to_month_start(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    """No `income_anchor_category_id` preference → month-start window."""
    # Deliberately do NOT bind an anchor preference. The seed has budgets +
    # a Jan 25 salary that would otherwise shift the window.
    s = bs.month_summary(conn, USER_ID, 2026, 1, today=date(2026, 1, 30), base_currency="PLN")
    by_cat = {line.category_id: line for line in s.lines}
    # Month-start window: Groceries 70_000, Rent 310_000.
    assert by_cat[seed["groceries"]].spent_minor == 70_000
    assert by_cat[seed["rent"]].spent_minor == 310_000


def test_budgeted_remaining_formula_consistency(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    """remaining_minor == budgeted_minor - spent_minor on anchor-shifted window."""
    _bind_anchor(conn, seed["salary"])
    s = bs.month_summary(conn, USER_ID, 2026, 1, today=date(2026, 1, 30), base_currency="PLN")
    for line in s.lines:
        if line.budgeted_minor is None:
            assert line.remaining_minor is None
        else:
            assert line.remaining_minor == line.budgeted_minor - line.spent_minor
    # Headline totals: spent_total sums only budgeted lines (existing invariant).
    budgeted_total = sum(line.budgeted_minor or 0 for line in s.lines)
    spent_total = sum(line.spent_minor for line in s.lines if line.budgeted_minor is not None)
    assert s.totals.budgeted_minor == budgeted_total
    assert s.totals.spent_minor == spent_total


# ---------------------------------------------------------------------------
# ADR-0064 — fiscal_month_for: landing month follows the paycheck cycle
# ---------------------------------------------------------------------------
def test_fiscal_month_for_returns_last_anchor_month(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    """Anchor Jan 25, today Feb 2: period Jan 25..Feb 25 is mostly February (ADR-0138)."""
    _bind_anchor(conn, seed["salary"])
    assert bs.fiscal_month_for(conn, USER_ID, date(2026, 2, 2)) == (2026, 2)


def test_fiscal_month_for_no_anchor_falls_back_to_calendar_month(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    """No anchor preference → calendar month."""
    assert bs.fiscal_month_for(conn, USER_ID, date(2026, 11, 1)) == (2026, 11)


def test_fiscal_month_for_no_prior_anchor_txn_falls_back(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    """Anchor configured but no promoted anchor txn on-or-before today → calendar month."""
    _bind_anchor(conn, seed["salary"])
    # Seed's salary txn is Jan 25 2026. Query for a date before it.
    assert bs.fiscal_month_for(conn, USER_ID, date(2026, 1, 1)) == (2026, 1)


def test_fiscal_month_for_picks_latest_of_multiple_anchors(conn: sqlite3.Connection) -> None:
    """Two promoted anchor txns → month of the most recent on-or-before today."""
    checking = accounts.create(
        conn, USER_ID, NewAccount(name="Checking", currency="PLN", opening_balance=0)
    ).id
    salary = categories.create(
        conn, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    ).id
    _bind_anchor(conn, salary)
    transactions.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 10, 7),
            category_id=salary,
            account_id=checking,
            amount=1_000_000,
        ),
    )
    transactions.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 9, 4),
            category_id=salary,
            account_id=checking,
            amount=1_000_000,
        ),
    )
    assert bs.fiscal_month_for(conn, USER_ID, date(2026, 11, 1)) == (2026, 10)
    # Today pinned before Oct 7 → previous (Sep) anchor wins.
    assert bs.fiscal_month_for(conn, USER_ID, date(2026, 10, 6)) == (2026, 9)


# ---------------------------------------------------------------------------
# T-FIX1 (ADR-0085) — only budgeted categories' commitments reduce "left"
# ---------------------------------------------------------------------------
@pytest.fixture
def fix1_world(conn: sqlite3.Connection) -> dict[str, int]:
    """Budgeted Groceries + Fun; unbudgeted Rent + Subs; Salary anchor."""
    w: dict[str, int] = {}
    w["checking"] = accounts.create(
        conn, USER_ID, NewAccount(name="Checking", currency="PLN", opening_balance=0)
    ).id
    for key, name, direction in (
        ("groceries", "Groceries", Direction.EXPENSE),
        ("fun", "Fun", Direction.EXPENSE),
        ("rent", "Rent", Direction.EXPENSE),
        ("subs", "Subs", Direction.EXPENSE),
        ("salary", "Salary", Direction.INCOME),
    ):
        w[key] = categories.create(conn, USER_ID, NewCategory(name=name, direction=direction)).id
    budgets.set_default(conn, USER_ID, NewBudgetDefault(category_id=w["groceries"], amount=200_000))
    budgets.set_default(conn, USER_ID, NewBudgetDefault(category_id=w["fun"], amount=100_000))
    _bind_anchor(conn, w["salary"])
    return w


def _plan(conn: sqlite3.Connection, w: dict[str, int], key: str, day: date, amount: int) -> int:
    return planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=day,
            category_id=w[key],
            account_id=w["checking"],
            amount=amount,
        ),
    ).id


def test_unbudgeted_planned_does_not_reduce_remaining(
    conn: sqlite3.Connection, fix1_world: dict[str, int]
) -> None:
    w = fix1_world
    _plan(conn, w, "salary", date(2026, 11, 25), 500_000)
    _plan(conn, w, "rent", date(2026, 11, 10), 350_000)
    s = bs.month_summary(conn, USER_ID, 2026, 11, today=date(2026, 11, 6), base_currency="PLN")
    assert s.totals.committed_minor == 0
    assert s.totals.unbudgeted_committed_minor == 350_000
    assert s.totals.remaining_minor == 300_000
    assert s.days_until_next_income == 19
    assert s.left_daily_spend_minor == 15_789  # 300_000 / 19, half-even


def test_unbudgeted_recurring_does_not_reduce_remaining(
    conn: sqlite3.Connection, fix1_world: dict[str, int]
) -> None:
    w = fix1_world
    _plan(conn, w, "salary", date(2026, 11, 25), 500_000)
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 11, 15),
            category_id=w["subs"],
            account_id=w["checking"],
            default_amount=60_000,
        ),
    )
    recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=date(2026, 11, 15)))
    s = bs.month_summary(conn, USER_ID, 2026, 11, today=date(2026, 11, 6), base_currency="PLN")
    assert s.totals.committed_minor == 0
    assert s.totals.unbudgeted_committed_minor == 60_000
    assert s.totals.remaining_minor == 300_000


def test_budgeted_planned_still_reduces_remaining(
    conn: sqlite3.Connection, fix1_world: dict[str, int]
) -> None:
    w = fix1_world
    _plan(conn, w, "salary", date(2026, 11, 25), 500_000)
    _plan(conn, w, "groceries", date(2026, 11, 12), 40_000)
    _plan(conn, w, "rent", date(2026, 11, 10), 350_000)
    s = bs.month_summary(conn, USER_ID, 2026, 11, today=date(2026, 11, 6), base_currency="PLN")
    assert s.totals.committed_minor == 40_000
    assert s.totals.unbudgeted_committed_minor == 350_000
    assert s.totals.remaining_minor == 300_000 - 40_000


@pytest.mark.parametrize(("key", "amount"), [("groceries", 40_000), ("rent", 350_000)])
def test_promotion_is_net_zero_on_remaining(
    conn: sqlite3.Connection, fix1_world: dict[str, int], key: str, amount: int
) -> None:
    w = fix1_world
    _plan(conn, w, "salary", date(2026, 11, 25), 500_000)
    pid = _plan(conn, w, key, date(2026, 11, 6), amount)
    before = bs.month_summary(conn, USER_ID, 2026, 11, today=date(2026, 11, 6), base_currency="PLN")
    planned_svc.promote_to_actual(
        conn, USER_ID, pid, planned_svc.PromotionEdits(operation_date=date(2026, 11, 6))
    )
    after = bs.month_summary(conn, USER_ID, 2026, 11, today=date(2026, 11, 6), base_currency="PLN")
    assert after.totals.remaining_minor == before.totals.remaining_minor
    assert after.totals.committed_minor + after.totals.unbudgeted_committed_minor == 0


def test_early_anchor_promotion_regression(
    conn: sqlite3.Connection, fix1_world: dict[str, int]
) -> None:
    """Promoting the cutoff row a day early must not swallow unbudgeted bills."""
    w = fix1_world
    old = _plan(conn, w, "salary", date(2026, 10, 7), 500_000)
    cut = _plan(conn, w, "salary", date(2026, 11, 7), 500_000)
    _plan(conn, w, "rent", date(2026, 11, 10), 350_000)
    _plan(conn, w, "subs", date(2026, 11, 15), 60_000)
    _plan(conn, w, "subs", date(2026, 11, 25), 40_000)
    _plan(conn, w, "salary", date(2026, 12, 7), 500_000)
    planned_svc.promote_to_actual(
        conn, USER_ID, old, planned_svc.PromotionEdits(operation_date=date(2026, 10, 7))
    )
    planned_svc.promote_to_actual(
        conn, USER_ID, cut, planned_svc.PromotionEdits(operation_date=date(2026, 11, 6))
    )
    s = bs.month_summary(conn, USER_ID, 2026, 11, today=date(2026, 11, 6), base_currency="PLN")
    assert s.totals.spent_minor == 0
    assert s.totals.committed_minor == 0
    assert s.totals.unbudgeted_committed_minor == 450_000
    assert s.totals.remaining_minor == s.totals.budgeted_minor == 300_000


def test_recurring_counted_once_per_occurrence_across_long_window(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    """Window clamp to max(next_due, start) must not shift the cadence anchor."""
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 5),
            category_id=committed_world["rent"],
            account_id=committed_world["checking"],
            default_amount=100_000,
        ),
    )
    recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=date(2026, 2, 5)))
    split = bs.committed_split_in_window(
        conn,
        USER_ID,
        start=date(2026, 2, 20),
        end=date(2026, 5, 20),
        budgeted_category_ids=frozenset({committed_world["rent"]}),
        today=clock.utc_now().date(),
        base_currency="PLN",
    )
    # Mar 5, Apr 5, May 5 only (Feb 5 is before the window).
    assert split == (300_000, 0)
    total = bs.committed_in_window(
        conn,
        USER_ID,
        start=date(2026, 2, 20),
        end=date(2026, 5, 20),
        today=clock.utc_now().date(),
        base_currency="PLN",
    )
    assert total == 300_000


# ---------------------------------------------------------------------------
# ADR-0105: committed includes every overdue unpromoted item (T-D115)
# ---------------------------------------------------------------------------
_OVERDUE_TODAY = date(2026, 2, 20)


def _planned_expense(
    conn: sqlite3.Connection, world: dict[str, int], cat: str, on: date, amount: int
) -> None:
    planned.create(
        conn,
        USER_ID,
        NewPlannedTransaction(
            operation_date=on,
            category_id=world[cat],
            account_id=world["checking"],
            amount=amount,
        ),
    )


def _overdue_rule(
    conn: sqlite3.Connection, world: dict[str, int], cat: str, next_due: date, amount: int
) -> None:
    rule = recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=next_due,
            category_id=world[cat],
            account_id=world["checking"],
            default_amount=amount,
        ),
    )
    recurring.update_rule(conn, USER_ID, rule.id, PatchRecurringRule(next_due=next_due))


def test_committed_in_window_unbounded_start_counts_all_overdue_planned(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    _planned_expense(conn, committed_world, "groceries", date(2025, 6, 1), 1_000)
    _planned_expense(conn, committed_world, "groceries", date(2026, 2, 19), 2_000)
    _planned_expense(conn, committed_world, "groceries", date(2026, 2, 28), 4_000)
    total = bs.committed_in_window(
        conn,
        USER_ID,
        start=None,
        end=date(2026, 2, 25),
        today=clock.utc_now().date(),
        base_currency="PLN",
    )
    assert total == 3_000


def test_committed_in_window_unbounded_start_expands_recurring_from_next_due(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    # Monthly rent overdue since Dec 5: Dec 5, Jan 5, Feb 5 all still owed.
    _overdue_rule(conn, committed_world, "rent", date(2025, 12, 5), 300_000)
    total = bs.committed_in_window(
        conn,
        USER_ID,
        start=None,
        end=date(2026, 2, 25),
        today=clock.utc_now().date(),
        base_currency="PLN",
    )
    assert total == 900_000


def test_month_summary_committed_includes_overdue_planned_any_age(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    """Overdue (before today, even before the period) + due-today + upcoming all count."""
    _planned_expense(conn, committed_world, "groceries", date(2025, 11, 3), 1_000)
    _planned_expense(conn, committed_world, "groceries", date(2026, 2, 10), 2_000)
    _planned_expense(conn, committed_world, "groceries", _OVERDUE_TODAY, 4_000)
    _planned_expense(conn, committed_world, "groceries", date(2026, 2, 26), 8_000)
    s = bs.month_summary(conn, USER_ID, 2026, 2, today=_OVERDUE_TODAY, base_currency="PLN")
    assert s.totals.committed_minor == 15_000
    assert s.totals.remaining_minor == 400_000 - 15_000


def test_month_summary_committed_includes_overdue_recurring(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    _overdue_rule(conn, committed_world, "rent", date(2026, 1, 5), 300_000)
    s = bs.month_summary(conn, USER_ID, 2026, 2, today=_OVERDUE_TODAY, base_currency="PLN")
    # Jan 5 + Feb 5 (both overdue); Mar 5 is outside [.., end of month).
    assert s.totals.committed_minor == 600_000


def test_month_summary_overdue_unbudgeted_goes_to_unbudgeted_committed(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    misc = categories.create(
        conn, USER_ID, NewCategory(name="Misc", direction=Direction.EXPENSE)
    ).id
    world = {**committed_world, "misc": misc}
    _planned_expense(conn, world, "misc", date(2026, 2, 1), 5_000)
    _overdue_rule(conn, world, "misc", date(2026, 2, 15), 700)
    s = bs.month_summary(conn, USER_ID, 2026, 2, today=_OVERDUE_TODAY, base_currency="PLN")
    assert s.totals.committed_minor == 0
    assert s.totals.unbudgeted_committed_minor == 5_700
    assert s.totals.remaining_minor == 400_000


def test_month_summary_promoted_overdue_planned_not_committed(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    _planned_expense(conn, committed_world, "groceries", date(2026, 2, 10), 2_000)
    row = planned.list_filtered(conn, USER_ID, PlannedFilter(promoted=False))[0]
    txn = transactions.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 2, 10),
            category_id=committed_world["groceries"],
            account_id=committed_world["checking"],
            amount=2_000,
        ),
    )
    planned.stamp_promotion(conn, USER_ID, row.id, txn.id)
    s = bs.month_summary(conn, USER_ID, 2026, 2, today=_OVERDUE_TODAY, base_currency="PLN")
    assert s.totals.committed_minor == 0
    assert s.totals.spent_minor == 2_000


# ---------------------------------------------------------------------------
# ADR-0138 / OQ-14: payday opens the new period
# ---------------------------------------------------------------------------
def _salary_period_fixture(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    _bind_anchor(conn, seed["salary"])
    for day in (date(2026, 10, 25),):
        transactions.create(
            conn,
            USER_ID,
            NewTransaction(
                operation_date=day,
                category_id=seed["salary"],
                account_id=seed["checking"],
                amount=500_000,
            ),
        )
    for day in (date(2026, 11, 25), date(2026, 12, 25)):
        planned.create(
            conn,
            USER_ID,
            NewPlannedTransaction(
                operation_date=day,
                category_id=seed["salary"],
                account_id=seed["checking"],
                amount=500_000,
                description="salary",
            ),
        )
    transactions.create(
        conn,
        USER_ID,
        NewTransaction(
            operation_date=date(2026, 11, 1),
            category_id=seed["groceries"],
            account_id=seed["checking"],
            amount=20_000,
        ),
    )


def test_on_payday_budget_uses_the_new_period_not_old_leftovers(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    _salary_period_fixture(conn, seed)
    payday = date(2026, 11, 25)
    s = bs.month_summary(conn, USER_ID, 2026, 11, today=payday, base_currency="PLN")
    assert s.period_start == payday
    assert s.next_income_date == date(2026, 12, 25)
    assert s.days_until_next_income == 30
    # The Nov 1 grocery spend belongs to the old period.
    assert s.totals.spent_minor == 0
    assert bs.resolve_period_start(conn, USER_ID, payday) == payday


def test_day_before_payday_is_still_the_old_period(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    _salary_period_fixture(conn, seed)
    s = bs.month_summary(conn, USER_ID, 2026, 11, today=date(2026, 11, 24), base_currency="PLN")
    assert s.period_start == date(2026, 10, 25)
    assert s.next_income_date == date(2026, 11, 25)
    assert s.days_until_next_income == 1
    assert s.totals.spent_minor == 20_000


def test_fiscal_month_label_is_the_month_with_most_days(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    _salary_period_fixture(conn, seed)
    # Oct 25 to Nov 25: 7 days in Oct, 25 in Nov -> November.
    assert bs.fiscal_month_for(conn, USER_ID, date(2026, 11, 3)) == (2026, 11)
    # Nov 25 to Dec 25 starts on payday (planned, not landed): still the Oct window until it lands.
    assert bs.fiscal_month_for(conn, USER_ID, date(2026, 11, 25)) == (2026, 11)


def test_picker_non_current_month_clamps_anchor_day_and_zeroes_committed(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    _bind_anchor(conn, seed["salary"])
    recurring.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            category_id=seed["salary"],
            account_id=seed["checking"],
            default_amount=500_000,
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 30),
            day_of_month=30,
            default_description="pay",
        ),
    )
    today = date(2026, 1, 31)
    picked = bs.resolve_picker_month(conn, USER_ID, today, year_raw="2026", month_raw="2")
    s = bs.month_summary_for_picker(conn, USER_ID, picked, today, base_currency="PLN")
    assert s.period_start == date(2026, 2, 28)  # day 30 clamped, not capped at 28 for Jan/Mar
    assert s.next_income_date == date(2026, 3, 30)
    assert s.totals.committed_minor == 0
    assert (picked.prev_year, picked.prev_month, picked.next_month) == (2026, 1, 3)


def test_picker_rejects_bad_query_values(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    today = date(2026, 3, 10)
    for year_raw, month_raw in (("x", "3"), ("2026", "13"), ("2026", "0")):
        picked = bs.resolve_picker_month(
            conn, USER_ID, today, year_raw=year_raw, month_raw=month_raw
        )
        assert (picked.year, picked.month) == (2026, 3)
