# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""Isolation cases for forecast, recurring, planned, recurring_formula, categories, reconciliation and promotion.

Same world and conventions as ``_isolation_read_cases.py``. Mutating cases run against a fresh database per test.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import sqlite3

import httpx
import pytest

from budget_planner.config import Settings
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import NewPlannedTransaction, PlannedFilter
from budget_planner.domain.recurring import AmountFormula, RecurringRule
from budget_planner.domain.transactions import TransactionFilter
from budget_planner.repositories import (
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)
from budget_planner.services import (
    _promotion,
    categories,
    forecast,
    planned,
    reconciliation,
    recurring,
    recurring_formula as formula_svc,
)
from tests.unit.services._isolation_registry import covers
from tests.unit.services.conftest import (
    EXPENSE_RULE_DUE,
    INCOME_RULE_DUE,
    OTHER_BALANCE,
    OTHER_ID,
    OWNER_BALANCE,
    OWNER_ID,
    WORLD_DAY,
    WORLD_TODAY,
    OwnedRows,
    World,
)

T = WORLD_TODAY
HORIZON_DAYS = 25  # 2026-11-12 .. 2026-12-07
PROMOTE_DAY = dt.date(2026, 11, 20)


def _rows(world: World, user_id: int) -> OwnedRows:
    return world.owner if user_id == OWNER_ID else world.other


def _rule(conn: sqlite3.Connection, user_id: int, rule_id: int) -> RecurringRule:
    rule = recurring_repo.find_rule(conn, user_id, rule_id, include_deleted=True)
    assert rule is not None
    return rule


def _income_formula(category_id: int) -> AmountFormula:
    term = formula_svc.build_term(
        sign="+", coefficient_percent="100", source_category_ids=(category_id,)
    )
    return formula_svc.build_formula([term])


def _count_txns(conn: sqlite3.Connection, user_id: int) -> int:
    return int(
        conn.execute(
            "SELECT COUNT(*) FROM transactions WHERE user_id = ? AND deleted_at IS NULL", (user_id,)
        ).fetchone()[0]
    )


# --- forecast ----------------------------------------------------------------------------------------------------


def _totals(series: forecast.ForecastSeries, *days: dt.date) -> list[int]:
    by_date = {d.on_date: d.totals_base_minor for d in series.days}
    return [by_date[d] for d in days]


_CHECK_DAYS = (T, dt.date(2026, 11, 13), EXPENSE_RULE_DUE, INCOME_RULE_DUE)


@covers("forecast.forecast")
def _case_forecast(conn: sqlite3.Connection, world: World) -> None:
    # The budget overlay is disabled: its numbers are in flux with T-Q206 (Q-002); explicit events are exact.
    with httpx.Client() as http:
        for user_id, balance in (
            (OWNER_ID, OWNER_BALANCE - 1_000),
            (OTHER_ID, OTHER_BALANCE - 2_000),
        ):
            series = forecast.forecast(
                conn, user_id, http, T, HORIZON_DAYS, "PLN", include_budget_overlay=False
            )
            u = user_id
            assert len(series.days) == HORIZON_DAYS + 1
            assert _totals(series, *_CHECK_DAYS) == [
                balance,
                balance - 500 * u,
                balance - 500 * u - 700 * u,
                balance - 500 * u - 700 * u + 5_000 * u,
            ]
            accounts = {p.account_id for day in series.days for p in day.by_account}
            assert accounts == {_rows(world, user_id).account_id}  # no dead / foreign accounts


@covers("forecast.forecast_monthly")
def _case_forecast_monthly(conn: sqlite3.Connection, world: World) -> None:
    with httpx.Client() as http:
        for user_id in (OWNER_ID, OTHER_ID):
            u = user_id
            months = forecast.forecast_monthly(conn, user_id, http, T, 2, "PLN").months
            assert [(m.month, m.income_base_minor, m.expense_base_minor) for m in months] == [
                (dt.date(2026, 11, 1), 0, 1_200 * u),
                (dt.date(2026, 12, 1), 5_000 * u, 700 * u),
            ]


@covers("forecast.monthly_projection")
def _case_monthly_projection(conn: sqlite3.Connection, world: World) -> None:
    for user_id in (OWNER_ID, OTHER_ID):
        u = user_id
        points = forecast.monthly_projection(conn, user_id, Settings(_env_file=None), T, 2)
        assert [(p.label, p.income_minor, p.expense_minor) for p in points] == [
            ("Nov 2026", 0, 1_200 * u),
            ("Dec 2026", 5_000 * u, 700 * u),
        ]


# --- recurring ---------------------------------------------------------------------------------------------------


@covers("recurring.expand_unpromoted")
def _case_expand_unpromoted(conn: sqlite3.Connection, world: World) -> None:
    window = (dt.date(2026, 11, 1), dt.date(2026, 12, 31))
    for user_id in (OWNER_ID, OTHER_ID):
        rows = _rows(world, user_id)
        rule = _rule(conn, user_id, rows.rule_id)
        occs = recurring.expand_unpromoted(conn, user_id, rule, [], *window)
        assert [(o.occurrence_date, o.amount, o.account_id) for o in occs] == [
            (EXPENSE_RULE_DUE, 700 * user_id, rows.account_id),
            (dt.date(2026, 12, 15), 700 * user_id, rows.account_id),
        ]
    assert world.tombstones is not None
    inactive = _rule(conn, OWNER_ID, world.tombstones.inactive_rule_id)
    assert (
        recurring.expand_unpromoted(conn, OWNER_ID, inactive, [], *window) == ()
    )  # inactive rules expand to nothing


@covers("recurring.linked_occurrence_keys")
def _case_linked_occurrence_keys(conn: sqlite3.Connection, world: World) -> None:
    for user_id in (OWNER_ID, OTHER_ID):
        rows = _rows(world, user_id)
        planned_repo.create(
            conn,
            user_id,
            NewPlannedTransaction(
                operation_date=dt.date(2026, 11, 16),
                category_id=rows.category_id,
                account_id=rows.account_id,
                amount=1,
                recurring_rule_id=rows.rule_id,
                occurrence_date=EXPENSE_RULE_DUE,
            ),
        )
    assert world.tombstones is not None
    dead = planned_repo.create(
        conn,
        OWNER_ID,
        NewPlannedTransaction(
            operation_date=dt.date(2026, 11, 17),
            category_id=world.owner.category_id,
            account_id=world.owner.account_id,
            amount=1,
            recurring_rule_id=world.tombstones.inactive_rule_id,
            occurrence_date=EXPENSE_RULE_DUE,
        ),
    )
    planned_repo.soft_delete(conn, OWNER_ID, dead.id)
    assert recurring.linked_occurrence_keys(conn, OWNER_ID) == frozenset(
        {(world.owner.rule_id, EXPENSE_RULE_DUE)}
    )
    assert recurring.linked_occurrence_keys(conn, OTHER_ID) == frozenset(
        {(world.other.rule_id, EXPENSE_RULE_DUE)}
    )


@covers("recurring.promote_recurring")
def _case_promote_recurring(conn: sqlite3.Connection, world: World) -> None:
    assert world.tombstones is not None
    edits = recurring.PromotionEdits()
    with pytest.raises(recurring.RecurringNotFoundError):
        recurring.promote_recurring(conn, OTHER_ID, world.owner.rule_id, edits)
    with pytest.raises(recurring.RecurringNotFoundError):  # soft-deleted rule
        recurring.promote_recurring(conn, OWNER_ID, world.tombstones.deleted_rule_id, edits)
    with pytest.raises(recurring.InactiveRecurringError):
        recurring.promote_recurring(conn, OWNER_ID, world.tombstones.inactive_rule_id, edits)
    assert _rule(conn, OWNER_ID, world.owner.rule_id).next_due == EXPENSE_RULE_DUE  # nothing moved
    txn = recurring.promote_recurring(conn, OWNER_ID, world.owner.rule_id, edits)
    assert (txn.amount, txn.operation_date, txn.account_id) == (
        700,
        EXPENSE_RULE_DUE,
        world.owner.account_id,
    )
    assert _rule(conn, OWNER_ID, world.owner.rule_id).next_due == dt.date(2026, 12, 15)
    assert _rule(conn, OTHER_ID, world.other.rule_id).next_due == EXPENSE_RULE_DUE


@covers("recurring.skip_and_advance")
def _case_skip_and_advance(conn: sqlite3.Connection, world: World) -> None:
    assert world.tombstones is not None
    with pytest.raises(recurring.RecurringNotFoundError):
        recurring.skip_and_advance(conn, OTHER_ID, world.owner.rule_id)
    with pytest.raises(recurring.InactiveRecurringError):
        recurring.skip_and_advance(conn, OWNER_ID, world.tombstones.inactive_rule_id)
    assert recurring.skip_and_advance(conn, OWNER_ID, world.owner.rule_id) == dt.date(2026, 12, 15)
    assert _rule(conn, OTHER_ID, world.other.rule_id).next_due == EXPENSE_RULE_DUE


@covers("recurring.batch_promote_due")
def _case_recurring_batch_promote_due(conn: sqlite3.Connection, world: World) -> None:
    before_other = _count_txns(conn, OTHER_ID)
    result = recurring.batch_promote_due(conn, OWNER_ID, PROMOTE_DAY)
    # Only the owner's live, active, due rule: not the income rule (due 12-01), the inactive or deleted rules, or user 2's.
    assert result.advanced_rule_ids == (world.owner.rule_id,)
    assert len(result.promoted_txn_ids) == 1
    assert result.skipped_rule_ids == ()
    promoted = transactions_repo.find_by_id(conn, OWNER_ID, result.promoted_txn_ids[0])
    assert promoted is not None
    assert promoted.amount == 700
    assert _count_txns(conn, OTHER_ID) == before_other
    assert _rule(conn, OTHER_ID, world.other.rule_id).next_due == EXPENSE_RULE_DUE


# --- planned -----------------------------------------------------------------------------------------------------


def _planned_ids(conn: sqlite3.Connection, user_id: int) -> set[int | None]:
    window = PlannedFilter(date_from=dt.date(2026, 11, 1), date_to=dt.date(2026, 11, 30))
    return {v.persisted_id for v in planned.list_planned(conn, user_id, window)}


@covers("planned.list_planned")
def _case_list_planned(conn: sqlite3.Connection, world: World) -> None:
    assert _planned_ids(conn, OWNER_ID) == {
        world.owner.planned_id
    }  # the soft-deleted planned row is excluded
    assert _planned_ids(conn, OTHER_ID) == {world.other.planned_id}
    view = planned.list_planned(
        conn, OWNER_ID, PlannedFilter(date_from=dt.date(2026, 11, 1), date_to=dt.date(2026, 11, 30))
    )[0]
    assert (view.amount_minor, view.operation_date, view.account_id) == (
        500,
        WORLD_DAY + dt.timedelta(days=3),
        world.owner.account_id,
    )


@covers("planned.promote_to_actual")
def _case_promote_to_actual(conn: sqlite3.Connection, world: World) -> None:
    assert world.tombstones is not None
    edits = planned.PromotionEdits()
    with pytest.raises(planned.PlannedNotFoundError):
        planned.promote_to_actual(conn, OTHER_ID, world.owner.planned_id, edits)
    with pytest.raises(planned.CannotPromoteDeletedError):
        planned.promote_to_actual(conn, OWNER_ID, world.tombstones.planned_id, edits)
    before_other = _count_txns(conn, OTHER_ID)
    txn = planned.promote_to_actual(conn, OWNER_ID, world.owner.planned_id, edits)
    assert (txn.amount, txn.account_id, txn.user_id) == (500, world.owner.account_id, OWNER_ID)
    assert _count_txns(conn, OTHER_ID) == before_other
    with pytest.raises(planned.AlreadyPromotedError):
        planned.promote_to_actual(conn, OWNER_ID, world.owner.planned_id, edits)


@covers("planned.batch_promote_due")
def _case_planned_batch_promote_due(conn: sqlite3.Connection, world: World) -> None:
    before_other = _count_txns(conn, OTHER_ID)
    result = planned.batch_promote_due(conn, OWNER_ID, PROMOTE_DAY)
    assert result.promoted_planned_ids == (
        world.owner.planned_id,
    )  # not the soft-deleted 8000 row, not user 2's
    assert len(result.promoted_txn_ids) == 1
    assert _count_txns(conn, OTHER_ID) == before_other
    still_open = planned_repo.list_filtered(conn, OTHER_ID, PlannedFilter(promoted=False))
    assert [r.id for r in still_open] == [world.other.planned_id]


# --- recurring_formula -------------------------------------------------------------------------------------------

_DEC = dt.date(2026, 12, 10)


@covers("recurring_formula.compute_formula_amount")
def _case_compute_formula_amount(conn: sqlite3.Connection, world: World) -> None:
    formula = _income_formula(world.owner.income_category_id)
    assert formula_svc.compute_formula_amount(conn, OWNER_ID, formula, 2026, 12) == 5_000
    assert (
        formula_svc.compute_formula_amount(conn, OWNER_ID, formula, 2026, 11) == 0
    )  # no occurrence yet
    assert (
        formula_svc.compute_formula_amount(conn, OTHER_ID, formula, 2026, 12) == 0
    )  # not user 2's category
    other = _income_formula(world.other.income_category_id)
    assert formula_svc.compute_formula_amount(conn, OTHER_ID, other, 2026, 12) == 10_000
    assert formula_svc.compute_formula_amount(conn, OWNER_ID, other, 2026, 12) == 0


@covers("recurring_formula.resolve_rule_amount")
def _case_resolve_rule_amount(conn: sqlite3.Connection, world: World) -> None:
    fixed = _rule(conn, OWNER_ID, world.owner.rule_id)
    assert formula_svc.resolve_rule_amount(conn, OWNER_ID, fixed, _DEC) == 700
    with_formula = dataclasses.replace(
        fixed, amount_formula=_income_formula(world.owner.income_category_id)
    )
    assert formula_svc.resolve_rule_amount(conn, OWNER_ID, with_formula, _DEC) == 5_000
    assert formula_svc.resolve_rule_amount(conn, OTHER_ID, with_formula, _DEC) == 0


@covers("recurring_formula.rt_expand")
def _case_rt_expand(conn: sqlite3.Connection, world: World) -> None:
    fixed = _rule(conn, OWNER_ID, world.owner.rule_id)
    with_formula = dataclasses.replace(
        fixed, amount_formula=_income_formula(world.owner.income_category_id)
    )
    window = (dt.date(2026, 12, 1), dt.date(2026, 12, 31))
    owner = formula_svc.rt_expand(conn, OWNER_ID, with_formula, [], *window)
    assert [(o.occurrence_date, o.amount) for o in owner] == [(dt.date(2026, 12, 15), 5_000)]
    other = formula_svc.rt_expand(conn, OTHER_ID, with_formula, [], *window)
    assert [(o.occurrence_date, o.amount) for o in other] == [(dt.date(2026, 12, 15), 0)]
    assert [o.amount for o in formula_svc.rt_expand(conn, OWNER_ID, fixed, [], *window)] == [700]


@covers("recurring_formula.validate_formula_sources")
def _case_validate_formula_sources(conn: sqlite3.Connection, world: World) -> None:
    own_category = _income_formula(
        world.owner.category_id
    )  # a rule may not source its own category
    with pytest.raises(formula_svc.FormulaCycleError):
        formula_svc.validate_formula_sources(
            conn, OWNER_ID, own_category, exclude_rule_id=world.owner.rule_id
        )
    # The same ids seen by user 2 match none of user 2's rules: no cycle can be found through foreign rows.
    formula_svc.validate_formula_sources(
        conn, OTHER_ID, own_category, exclude_rule_id=world.other.rule_id
    )
    assert world.tombstones is not None
    # The inactive rule shares the category but is skipped (active_only): the guard sees only the live rule.
    sources = _income_formula(world.owner.income_category_id)
    formula_svc.validate_formula_sources(
        conn, OWNER_ID, sources, exclude_rule_id=world.owner.rule_id
    )


@covers("recurring_formula.preview")
def _case_preview(conn: sqlite3.Connection, world: World) -> None:
    owner_terms = [formula_svc.DraftTerm("+", "100", (world.owner.income_category_id,))]
    assert formula_svc.preview(conn, OWNER_ID, _DEC, None, owner_terms) == formula_svc.PreviewOk(
        amount_minor=5_000
    )
    foreign = formula_svc.preview(conn, OTHER_ID, _DEC, None, owner_terms)
    assert isinstance(foreign, formula_svc.PreviewError)
    assert (foreign.code, foreign.offending_term_index) == ("invalid_source", 0)
    assert world.tombstones is not None
    dead = formula_svc.preview(
        conn,
        OWNER_ID,
        _DEC,
        None,
        [formula_svc.DraftTerm("+", "100", (world.tombstones.category_id,))],
    )
    assert isinstance(dead, formula_svc.PreviewError)
    assert dead.code == "invalid_source"


# --- categories --------------------------------------------------------------------------------------------------


@covers("categories.archive")
def _case_archive(conn: sqlite3.Connection, world: World) -> None:
    assert world.tombstones is not None
    with pytest.raises(categories.CategoryNotFoundError):
        categories.archive(conn, OTHER_ID, world.owner.category_id)
    with pytest.raises(categories.CategoryNotFoundError):  # already archived
        categories.archive(conn, OWNER_ID, world.tombstones.category_id)
    with pytest.raises(
        categories.CategoryHasLiveRulesError
    ):  # the live rule blocks block-mode; the inactive one does not count
        categories.archive(conn, OWNER_ID, world.owner.category_id, block_on_live_rules=True)
    archived = categories.archive(conn, OWNER_ID, world.owner.category_id)
    assert archived.deleted_at is not None
    live_other = categories_repo.find_by_id(conn, OTHER_ID, world.other.category_id)
    assert live_other is not None
    assert live_other.deleted_at is None


@covers("categories.restore")
def _case_restore(conn: sqlite3.Connection, world: World) -> None:
    assert world.tombstones is not None
    with pytest.raises(categories.CategoryNotFoundError):
        categories.restore(conn, OTHER_ID, world.tombstones.category_id)
    with pytest.raises(categories.CategoryNotFoundError):  # live category: nothing to restore
        categories.restore(conn, OWNER_ID, world.owner.category_id)
    restored = categories.restore(conn, OWNER_ID, world.tombstones.category_id)
    assert (restored.name, restored.deleted_at, restored.direction) == (
        "dead-category",
        None,
        Direction.EXPENSE,
    )


# --- reconciliation / promotion ---------------------------------------------------------------------------------


@covers("reconciliation.reconcile")
def _case_reconcile(conn: sqlite3.Connection, world: World) -> None:
    assert world.tombstones is not None
    with pytest.raises(reconciliation.AccountNotFoundError):
        reconciliation.reconcile(conn, OTHER_ID, world.owner.account_id, 1, T)
    with pytest.raises(reconciliation.CannotReconcileDeletedAccountError):
        reconciliation.reconcile(conn, OWNER_ID, world.tombstones.account_id, 1, T)
    target = OWNER_BALANCE
    txn = reconciliation.reconcile(
        conn, OWNER_ID, world.owner.account_id, target, T, category_id=world.owner.category_id
    )
    assert (txn.user_id, txn.account_id, txn.amount) == (OWNER_ID, world.owner.account_id, 1_000)
    other_txns = transactions_repo.list_filtered(conn, OTHER_ID, TransactionFilter())
    assert [t.amount for t in other_txns] == [2_000]  # user 2's ledger is untouched


@covers("_promotion.validate_promotion")
def _case_validate_promotion(conn: sqlite3.Connection, world: World) -> None:
    assert world.tombstones is not None

    def transit(dest: int) -> None:
        _promotion.validate_promotion(
            conn,
            OWNER_ID,
            direction=Direction.TRANSIT,
            account_id=world.owner.account_id,
            dest_account_id=dest,
            amount=5,
        )

    transit(world.owner.account_id)  # own account on both legs: valid
    with pytest.raises(_promotion.ValidationError):
        transit(world.other.account_id)  # user 2's account is invisible to user 1
    with pytest.raises(_promotion.ValidationError):
        transit(world.tombstones.account_id)  # a soft-deleted account is not a valid destination
