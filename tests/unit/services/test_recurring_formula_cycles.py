"""A formula rule that reads its own posting category, on create (T-UR10b, ADR-0047).

``validate_formula_sources`` knew a rule's id only on edit, so a new rule could source the category
it posts to (directly or through other rules) and save. The posting category closes that gap; an
already stored cycle no longer takes a listing page down: its amount is skipped, marked and logged.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.recurring import AmountFormula, FormulaTerm, NewRecurringRule
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    recurring as recurring_repo,
)
from budget_planner.services import recurring as recurring_svc
from budget_planner.services.recurring_formula import (
    DATES_ONLY,
    FORMULA_CYCLE_MARK,
    DraftTerm,
    FormulaCycleError,
    PreviewError,
    compute_savable_amount,
    live_rule_amount,
    preview,
    validate_formula_sources,
)
from tests.formula_fx_support import TARGET_CCY, formula_fx_of

USER_ID = 1


def _reads(*category_ids: int) -> AmountFormula:
    return AmountFormula(
        terms=(FormulaTerm(sign="+", coefficient_bps=1000, source_category_ids=category_ids),)
    )


@pytest.fixture
def world(conn: sqlite3.Connection) -> dict[str, int]:
    acc = accounts_repo.create(conn, USER_ID, NewAccount(name="Main", currency="PLN"))
    ids = {"acc": acc.id}
    for name, direction in (
        ("salary", Direction.INCOME),
        ("taxes", Direction.EXPENSE),
        ("savings", Direction.EXPENSE),
    ):
        ids[name] = categories_repo.create(
            conn, USER_ID, NewCategory(name=name, direction=direction)
        ).id
    return ids


def _rule(
    conn: sqlite3.Connection,
    ids: dict[str, int],
    category: str,
    formula: AmountFormula | None = None,
) -> int:
    return recurring_repo.create_rule(
        conn,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2099, 1, 1),
            category_id=ids[category],
            account_id=ids["acc"],
            default_amount=10_000,
            amount_formula=formula,
        ),
    ).id


def test_a_new_rule_cannot_source_its_own_posting_category(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    with pytest.raises(FormulaCycleError, match="its own category"):
        validate_formula_sources(
            conn, USER_ID, _reads(world["taxes"]), posting_category_id=world["taxes"]
        )


def test_a_new_rule_cannot_close_a_cycle_through_another_rule(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    # savings = 10 % of taxes; a new rule posting to taxes may not read savings
    savings_rule = _rule(conn, world, "savings", _reads(world["taxes"]))
    with pytest.raises(FormulaCycleError, match=f"via rule {savings_rule}"):
        validate_formula_sources(
            conn, USER_ID, _reads(world["savings"]), posting_category_id=world["taxes"]
        )


def test_a_new_rule_cannot_close_a_longer_cycle(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    # salary = 10 % of savings, savings = 10 % of taxes: taxes may not read salary
    _rule(conn, world, "salary", _reads(world["savings"]))
    _rule(conn, world, "savings", _reads(world["taxes"]))
    with pytest.raises(FormulaCycleError):
        validate_formula_sources(
            conn, USER_ID, _reads(world["salary"]), posting_category_id=world["taxes"]
        )


def test_an_acyclic_new_rule_passes(conn: sqlite3.Connection, world: dict[str, int]) -> None:
    _rule(conn, world, "salary")
    validate_formula_sources(
        conn, USER_ID, _reads(world["salary"]), posting_category_id=world["taxes"]
    )


def test_save_validation_and_preview_use_the_posting_category(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    _rule(conn, world, "taxes")
    fx = formula_fx_of(conn, USER_ID)
    with pytest.raises(FormulaCycleError):
        compute_savable_amount(
            conn,
            USER_ID,
            _reads(world["taxes"]),
            2026,
            11,
            fx=fx,
            target_ccy=TARGET_CCY,
            posting_category_id=world["taxes"],
        )
    result = preview(
        conn,
        USER_ID,
        date(2026, 11, 22),
        None,
        [DraftTerm("+", "10", (world["taxes"],))],
        fx=fx,
        target_ccy=TARGET_CCY,
        posting_category_id=world["taxes"],
    )
    assert isinstance(result, PreviewError)
    assert (result.code, result.message) == ("cycle", "a formula cannot reference its own category")


def test_a_stored_cycle_is_skipped_marked_and_logged(
    conn: sqlite3.Connection, world: dict[str, int], caplog: pytest.LogCaptureFixture
) -> None:
    # saved before the check existed: savings reads taxes and taxes reads savings
    taxes_rule = _rule(conn, world, "taxes", _reads(world["savings"]))
    savings_rule = _rule(conn, world, "savings", _reads(world["taxes"]))
    fx = formula_fx_of(conn, USER_ID)
    with caplog.at_level(logging.WARNING):
        items = recurring_svc.pending_occurrences(
            conn,
            USER_ID,
            fx=fx,
            start=date(2099, 1, 1),
            end=date(2099, 6, 1),
            today=date(2098, 12, 1),
            include_overdue=False,
        )
    marked = {(i.rule_id, i.amount, i.description) for i in items if i.rule_id is not None}
    assert marked == {
        (taxes_rule, 0, FORMULA_CYCLE_MARK),
        (savings_rule, 0, FORMULA_CYCLE_MARK),
    }
    assert f"formula cycle in recurring rule {taxes_rule}" in caplog.text
    # an expansion that reads no amounts is unaffected
    dates_only = recurring_svc.pending_occurrences(
        conn,
        USER_ID,
        fx=DATES_ONLY,
        start=date(2099, 1, 1),
        end=date(2099, 6, 1),
        today=date(2098, 12, 1),
        include_overdue=False,
    )
    assert {i.description for i in dates_only} == {""}


def test_live_amount_of_a_stored_cycle_is_zero_and_flagged_like_the_expansion(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    # Q25: both surfaces agree; the saved snapshot (100.00) is not shown for a cycle
    taxes_rule = _rule(conn, world, "taxes", _reads(world["savings"]))
    _rule(conn, world, "savings", _reads(world["taxes"]))
    fx = formula_fx_of(conn, USER_ID)
    rule = recurring_repo.find_rule(conn, USER_ID, taxes_rule)
    assert rule is not None
    assert live_rule_amount(conn, USER_ID, rule, date(2099, 1, 1), fx) == (0, True)
    expanded = recurring_svc.pending_occurrences(
        conn,
        USER_ID,
        fx=fx,
        start=date(2099, 1, 1),
        end=date(2099, 6, 1),
        today=date(2098, 12, 1),
        include_overdue=False,
    )
    assert {i.amount for i in expanded if i.rule_id == taxes_rule} == {0}


def test_live_amount_of_a_healthy_rule_is_not_flagged(
    conn: sqlite3.Connection, world: dict[str, int]
) -> None:
    fixed = _rule(conn, world, "salary")
    fx = formula_fx_of(conn, USER_ID)
    rule = recurring_repo.find_rule(conn, USER_ID, fixed)
    assert rule is not None
    assert live_rule_amount(conn, USER_ID, rule, date(2099, 1, 1), fx) == (10_000, False)
