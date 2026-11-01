"""Tests for the budget service (T-024 / T-120)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

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
from budget_planner.services import budget as bs, recurring as recurring_svc


@pytest.fixture
def seed(conn: sqlite3.Connection) -> dict[str, int]:
    checking = accounts.create(
        conn, NewAccount(name="Checking", currency="PLN", opening_balance=0)
    ).id
    groceries = categories.create(
        conn, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    ).id
    rent = categories.create(conn, NewCategory(name="Rent", direction=Direction.EXPENSE)).id
    utilities = categories.create(
        conn, NewCategory(name="Utilities", direction=Direction.EXPENSE)
    ).id
    gym = categories.create(conn, NewCategory(name="Gym", direction=Direction.EXPENSE)).id
    salary = categories.create(conn, NewCategory(name="Salary", direction=Direction.INCOME)).id

    budgets.set_default(conn, NewBudgetDefault(category_id=groceries, amount=120_000))
    budgets.set_default(conn, NewBudgetDefault(category_id=rent, amount=300_000))
    budgets.set_default(conn, NewBudgetDefault(category_id=utilities, amount=40_000))

    budgets.set_recurring(
        conn, NewBudgetRecurringOverride(category_id=rent, month=1, amount=310_000)
    )
    budgets.set_one_off(
        conn, NewBudgetOneOffOverride(category_id=utilities, year=2026, month=2, amount=60_000)
    )

    def _txn(d: date, cat: int, amount: int) -> int:
        return transactions.create(
            conn,
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
    assert bs.resolve_budget(conn, seed["groceries"], 2026, 3) == 120_000


def test_recurring_beats_default(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    assert bs.resolve_budget(conn, seed["rent"], 2026, 1) == 310_000


def test_recurring_only_in_its_month(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    assert bs.resolve_budget(conn, seed["rent"], 2026, 7) == 300_000


def test_one_off_beats_both(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    assert bs.resolve_budget(conn, seed["utilities"], 2026, 2) == 60_000


def test_one_off_single_year(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    assert bs.resolve_budget(conn, seed["utilities"], 2027, 2) == 40_000


def test_unbudgeted_returns_none(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    assert bs.resolve_budget(conn, seed["gym"], 2026, 3) is None


def test_zero_default_returns_zero(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    budgets.set_default(conn, NewBudgetDefault(category_id=seed["gym"], amount=0))
    assert bs.resolve_budget(conn, seed["gym"], 2026, 4) == 0


# ---------------------------------------------------------------------------
# month_summary
# ---------------------------------------------------------------------------
def test_january_summary(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    # today=Jan 31 so the paycheck window captures every January expense;
    # fixture does not bind an income anchor, so period_start = month start
    # per ADR-0041 fallback.
    s = bs.month_summary(conn, 2026, 1, today=date(2026, 1, 31))
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
    s = bs.month_summary(conn, 2026, 2, today=date(2026, 2, 15))
    by_cat = {line.category_id: line for line in s.lines}
    # Utilities one-off 60_000; spent 55_000; remaining 5_000.
    assert by_cat[seed["utilities"]].budgeted_minor == 60_000
    assert by_cat[seed["utilities"]].spent_minor == 55_000
    assert by_cat[seed["utilities"]].remaining_minor == 5000
    # Groceries delta vs Jan: 45_000 - 70_000 = -25_000.
    assert by_cat[seed["groceries"]].delta_vs_prev_month_minor == -25_000


def test_totals_exclude_unbudgeted(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    s = bs.month_summary(conn, 2026, 1, today=date(2026, 1, 31))
    # Budgeted: Rent 310k + Groceries 120k + Utilities 40k = 470k.
    assert s.totals.budgeted_minor == 470_000
    assert s.totals.spent_minor == 310_000 + 70_000 + 0
    assert s.totals.remaining_minor == 470_000 - (310_000 + 70_000)


def test_previous_month_rollover_january_to_december(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    s = bs.month_summary(conn, 2026, 1, today=date(2026, 1, 31))
    by_cat = {line.category_id: line for line in s.lines}
    # No Dec 2025 Groceries in fixture → delta = 70_000.
    assert by_cat[seed["groceries"]].delta_vs_prev_month_minor == 70_000


def test_avg_monthly_overall_uses_active_months(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    s = bs.month_summary(conn, 2026, 2, today=date(2026, 2, 15))
    by_cat = {line.category_id: line for line in s.lines}
    # Groceries active months: Nov 2025, Jan 2026, Feb 2026 → 3 months.
    # Sum = 35_000 + 70_000 + 45_000 = 150_000; avg = 50_000.
    assert by_cat[seed["groceries"]].avg_monthly_overall_minor == 50_000


def test_avg_this_year(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    s = bs.month_summary(conn, 2026, 2, today=date(2026, 2, 15))
    by_cat = {line.category_id: line for line in s.lines}
    # Groceries YTD through Feb: Jan 70_000 + Feb 45_000 = 115_000; / 2 = 57_500.
    assert by_cat[seed["groceries"]].avg_this_year_minor == 57_500


def test_soft_deleted_excluded(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    # Delete a January Groceries txn → spent + averages drop.
    cat_id = seed["groceries"]
    jan_txns = transactions.list_filtered(
        conn,
        TransactionFilter(
            date_from=date(2026, 1, 1), date_to=date(2026, 1, 31), category_ids=(cat_id,)
        ),
    )
    assert jan_txns
    transactions.soft_delete(conn, jan_txns[0].id)
    s = bs.month_summary(conn, 2026, 1, today=date(2026, 1, 31))
    by_cat = {line.category_id: line for line in s.lines}
    assert by_cat[cat_id].spent_minor == 70_000 - jan_txns[0].amount


def test_income_excluded_from_spent(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    s = bs.month_summary(conn, 2026, 1, today=date(2026, 1, 15))
    by_cat = {line.category_id: line for line in s.lines}
    # Salary category is income — should not appear in month_summary lines.
    assert seed["salary"] not in by_cat


def test_adjustment_excluded(conn: sqlite3.Connection, seed: dict[str, int]) -> None:
    adj_cat = categories.find_by_name(conn, "Reconciliation")
    assert adj_cat is not None
    transactions.create(
        conn,
        NewTransaction(
            operation_date=date(2026, 1, 10),
            category_id=adj_cat.id,
            account_id=seed["checking"],
            amount=-5000,
        ),
    )
    s = bs.month_summary(conn, 2026, 1, today=date(2026, 1, 31))
    # Adjustment direction excluded; Groceries spent unchanged at 70_000.
    by_cat = {line.category_id: line for line in s.lines}
    assert by_cat[seed["groceries"]].spent_minor == 70_000


def test_sort_order_budgeted_first_then_alpha(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    s = bs.month_summary(conn, 2026, 1, today=date(2026, 1, 15))
    # Budgeted lines first, then None-budget lines, each alpha by name.
    kinds = [line.budgeted_minor is None for line in s.lines]
    assert kinds == sorted(kinds)
    # Within budgeted group, names sorted.
    budgeted_names = [line.category_name for line in s.lines if line.budgeted_minor is not None]
    assert budgeted_names == sorted(budgeted_names)


def test_prev_year_month_rollover_december() -> None:
    assert bs.prev_year_month(2026, 1) == (2025, 12)
    assert bs.prev_year_month(2026, 7) == (2026, 6)


# ---------------------------------------------------------------------------
# T-120 — committed_in_window + MonthTotals.committed_minor
# ---------------------------------------------------------------------------
def test_committed_defaults_to_zero_without_recurring_or_planned(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    """Phase 9 budget fixtures have no planned/recurring rows → committed=0."""
    s = bs.month_summary(conn, 2026, 1, today=date(2026, 1, 31))
    assert s.totals.committed_minor == 0
    # Regression: remaining is still budgeted - spent when committed is zero.
    assert s.totals.remaining_minor == 470_000 - (310_000 + 70_000)


@pytest.fixture
def committed_world(conn: sqlite3.Connection) -> dict[str, int]:
    """A minimal expense + anchor world for exercising committed logic."""
    checking = accounts.create(
        conn, NewAccount(name="Checking", currency="PLN", opening_balance=0)
    ).id
    groceries = categories.create(
        conn, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    ).id
    rent = categories.create(conn, NewCategory(name="Rent", direction=Direction.EXPENSE)).id
    salary = categories.create(conn, NewCategory(name="Salary", direction=Direction.INCOME)).id
    # Baseline budgets so budgeted_total != 0 (otherwise committed is forced to 0).
    budgets.set_default(conn, NewBudgetDefault(category_id=groceries, amount=100_000))
    budgets.set_default(conn, NewBudgetDefault(category_id=rent, amount=300_000))
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
        NewPlannedTransaction(
            operation_date=date(2026, 2, 10),
            category_id=committed_world["groceries"],
            account_id=committed_world["checking"],
            amount=12_000,
            description="Market",
        ),
    )
    # Unpromoted planned expense inside [Feb 1, Feb 15).
    total = bs.committed_in_window(conn, start=date(2026, 2, 1), end=date(2026, 2, 15))
    assert total == 12_000
    # Promoted-row counterpart must NOT be counted.
    planned.create(
        conn,
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
        PlannedFilter(promoted=False, category_ids=(committed_world["groceries"],)),
    )
    assert rows
    # Reuse the real stamp-promotion path so repo invariants fire.
    txn = transactions.create(
        conn,
        NewTransaction(
            operation_date=date(2026, 2, 12),
            category_id=committed_world["groceries"],
            account_id=committed_world["checking"],
            amount=99_000,
        ),
    )
    planned.stamp_promotion(conn, rows[-1].id, txn.id)
    total_after = bs.committed_in_window(conn, start=date(2026, 2, 1), end=date(2026, 2, 15))
    # Only the first (unpromoted) planned row survives.
    assert total_after == 12_000


def test_committed_in_window_recurring_monthly_inside_window(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    rule = recurring.create_rule(
        conn,
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
    recurring.update_rule(conn, rule.id, PatchRecurringRule(next_due=date(2026, 2, 5)))
    total = bs.committed_in_window(conn, start=date(2026, 2, 1), end=date(2026, 2, 28))
    assert total == 300_000


def test_committed_in_window_recurring_end_date_cuts_mid_window(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    """A recurring rule whose end_date falls inside the window excludes
    occurrences after end_date."""
    recurring.create_rule(
        conn,
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
    total = bs.committed_in_window(conn, start=date(2026, 2, 1), end=date(2026, 3, 10))
    assert total == 300_000


def test_committed_in_window_override_adjusts_amount(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    rule = recurring.create_rule(
        conn,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 2, 5),
            category_id=committed_world["rent"],
            account_id=committed_world["checking"],
            default_amount=300_000,
            default_description="Rent",
        ),
    )
    recurring.update_rule(conn, rule.id, PatchRecurringRule(next_due=date(2026, 2, 5)))
    recurring.upsert_override(
        conn,
        NewRecurringOverride(
            rule_id=rule.id,
            occurrence_date=date(2026, 2, 5),
            state=OverrideState.OVERRIDDEN,
            amount_override=250_000,
        ),
    )
    total = bs.committed_in_window(conn, start=date(2026, 2, 1), end=date(2026, 2, 28))
    assert total == 250_000


def test_committed_in_window_skipped_override_excluded(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    rule = recurring.create_rule(
        conn,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 2, 5),
            category_id=committed_world["rent"],
            account_id=committed_world["checking"],
            default_amount=300_000,
        ),
    )
    recurring.update_rule(conn, rule.id, PatchRecurringRule(next_due=date(2026, 2, 5)))
    recurring.upsert_override(
        conn,
        NewRecurringOverride(
            rule_id=rule.id,
            occurrence_date=date(2026, 2, 5),
            state=OverrideState.SKIPPED,
        ),
    )
    total = bs.committed_in_window(conn, start=date(2026, 2, 1), end=date(2026, 2, 28))
    assert total == 0


def test_committed_in_window_excludes_non_expense_directions(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    """Income + transit + adjustment recurring/planned must not be counted."""
    # Planned income row — must be excluded.
    planned.create(
        conn,
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
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 2, 1),
            category_id=committed_world["salary"],
            account_id=committed_world["checking"],
            default_amount=500_000,
        ),
    )
    recurring.update_rule(conn, rule.id, PatchRecurringRule(next_due=date(2026, 2, 1)))
    total = bs.committed_in_window(conn, start=date(2026, 2, 1), end=date(2026, 2, 28))
    assert total == 0


def test_committed_in_window_empty_range_short_circuits(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    total = bs.committed_in_window(conn, start=date(2026, 2, 15), end=date(2026, 2, 15))
    assert total == 0


def test_month_summary_recurring_reduces_remaining_and_daily_spend(
    conn: sqlite3.Connection, committed_world: dict[str, int]
) -> None:
    """One recurring expense due inside window shaves remaining + daily spend."""
    preferences_repo.upsert(conn, 1, PREF_INCOME_ANCHOR_CATEGORY_ID, str(committed_world["salary"]))
    planned.create(
        conn,
        NewPlannedTransaction(
            operation_date=date(2026, 2, 25),
            category_id=committed_world["salary"],
            account_id=committed_world["checking"],
            amount=500_000,
        ),
    )
    rule = recurring.create_rule(
        conn,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 2, 20),
            category_id=committed_world["rent"],
            account_id=committed_world["checking"],
            default_amount=300_000,
        ),
    )
    recurring.update_rule(conn, rule.id, PatchRecurringRule(next_due=date(2026, 2, 20)))

    s = bs.month_summary(conn, 2026, 2, today=date(2026, 2, 15))
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
        NewPlannedTransaction(
            operation_date=date(2026, 2, 25),
            category_id=committed_world["salary"],
            account_id=committed_world["checking"],
            amount=500_000,
        ),
    )
    rule = recurring.create_rule(
        conn,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 2, 20),
            category_id=committed_world["rent"],
            account_id=committed_world["checking"],
            default_amount=300_000,
        ),
    )
    recurring.update_rule(conn, rule.id, PatchRecurringRule(next_due=date(2026, 2, 20)))

    before = bs.month_summary(conn, 2026, 2, today=date(2026, 2, 20))
    recurring_svc.promote_recurring(conn, rule.id, recurring_svc.PromotionEdits())
    after = bs.month_summary(conn, 2026, 2, today=date(2026, 2, 20))

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
    s = bs.month_summary(conn, 2026, 1, today=date(2026, 1, 30))
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
        conn, TransactionFilter(category_ids=(seed["salary"],))
    )
    for row in salary_rows:
        transactions.soft_delete(conn, row.id)

    # today=Jan 30 so the paycheck window would have shifted if a salary
    # existed. With no prior anchor row, fallback to month-start → the full
    # Groceries + Rent expenses up to today are summed.
    s = bs.month_summary(conn, 2026, 1, today=date(2026, 1, 30))
    by_cat = {line.category_id: line for line in s.lines}
    # Month-start window [Jan 1, Jan 30] catches all January expenses.
    assert by_cat[seed["groceries"]].spent_minor == 70_000
    assert by_cat[seed["rent"]].spent_minor == 310_000


def test_zero_budget_month_unchanged(conn: sqlite3.Connection) -> None:
    """Zero-budget months keep month-start fallback (no anchor side effects)."""
    checking = accounts.create(
        conn, NewAccount(name="Checking", currency="PLN", opening_balance=0)
    ).id
    groceries = categories.create(
        conn, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    ).id
    salary = categories.create(conn, NewCategory(name="Salary", direction=Direction.INCOME)).id
    # No budgets. Anchor bound + salary posted mid-month.
    _bind_anchor(conn, salary)
    transactions.create(
        conn,
        NewTransaction(
            operation_date=date(2026, 1, 10),
            category_id=salary,
            account_id=checking,
            amount=500_000,
        ),
    )
    transactions.create(
        conn,
        NewTransaction(
            operation_date=date(2026, 1, 5),
            category_id=groceries,
            account_id=checking,
            amount=20_000,
        ),
    )
    s = bs.month_summary(conn, 2026, 1, today=date(2026, 1, 20))
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
    s = bs.month_summary(conn, 2026, 1, today=date(2026, 1, 30))
    by_cat = {line.category_id: line for line in s.lines}
    # Month-start window: Groceries 70_000, Rent 310_000.
    assert by_cat[seed["groceries"]].spent_minor == 70_000
    assert by_cat[seed["rent"]].spent_minor == 310_000


def test_budgeted_remaining_formula_consistency(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    """remaining_minor == budgeted_minor - spent_minor on anchor-shifted window."""
    _bind_anchor(conn, seed["salary"])
    s = bs.month_summary(conn, 2026, 1, today=date(2026, 1, 30))
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
    """Last promoted anchor on Jan 25 + today Feb 2 → (2026, 1)."""
    _bind_anchor(conn, seed["salary"])
    assert bs.fiscal_month_for(conn, date(2026, 2, 2)) == (2026, 1)


def test_fiscal_month_for_no_anchor_falls_back_to_calendar_month(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    """No anchor preference → calendar month."""
    assert bs.fiscal_month_for(conn, date(2026, 11, 1)) == (2026, 11)


def test_fiscal_month_for_no_prior_anchor_txn_falls_back(
    conn: sqlite3.Connection, seed: dict[str, int]
) -> None:
    """Anchor configured but no promoted anchor txn on-or-before today → calendar month."""
    _bind_anchor(conn, seed["salary"])
    # Seed's salary txn is Jan 25 2026. Query for a date before it.
    assert bs.fiscal_month_for(conn, date(2026, 1, 1)) == (2026, 1)


def test_fiscal_month_for_picks_latest_of_multiple_anchors(conn: sqlite3.Connection) -> None:
    """Two promoted anchor txns → month of the most recent on-or-before today."""
    checking = accounts.create(
        conn, NewAccount(name="Checking", currency="PLN", opening_balance=0)
    ).id
    salary = categories.create(conn, NewCategory(name="Salary", direction=Direction.INCOME)).id
    _bind_anchor(conn, salary)
    transactions.create(
        conn,
        NewTransaction(
            operation_date=date(2026, 10, 7),
            category_id=salary,
            account_id=checking,
            amount=1_000_000,
        ),
    )
    transactions.create(
        conn,
        NewTransaction(
            operation_date=date(2026, 9, 4),
            category_id=salary,
            account_id=checking,
            amount=1_000_000,
        ),
    )
    assert bs.fiscal_month_for(conn, date(2026, 11, 1)) == (2026, 10)
    # Today pinned before Oct 7 → previous (Sep) anchor wins.
    assert bs.fiscal_month_for(conn, date(2026, 10, 6)) == (2026, 9)
