"""Mutant-kill tests for the formula / allocation logic (T-Q222, Q-016, ADR-0131).

Exact minor-unit values; DB-backed cases use the two-user worlds of T-Q221.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import sqlite3

import pytest

from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction, OverrideState
from budget_planner.domain.recurring import (
    AmountFormula,
    FormulaTerm,
    NewRecurringOverride,
    PatchRecurringRule,
    RecurringRule,
)
from budget_planner.repositories import (
    categories as categories_repo,
    recurring as recurring_repo,
)
from budget_planner.repositories._unaudited import set_inactive
from budget_planner.services import recurring_formula as formula_svc
from budget_planner.services.recurring_formula import (
    DraftTerm,
    FormulaCycleError,
    FormulaError,
    PreviewError,
    PreviewOk,
    _apply_coefficient,
    _month_bounds,
    _parse_sign,
    build_formula,
    build_term,
    compute_formula_amount,
    compute_savable_amount,
    parse_percent_to_bps,
    preview,
    resolve_rule_amount,
    rt_expand,
    validate_formula_sources,
)
from tests.unit.services.conftest import (
    EXPENSE_RULE_DUE,
    OTHER_ID,
    OWNER_ID,
    World,
    expense_rule_amount,
    seed_rule,
)

NOV = (2026, 11)
DEC = (2026, 12)


def _f(*terms: tuple[str, int, tuple[int, ...]]) -> AmountFormula:
    return AmountFormula(
        terms=tuple(
            FormulaTerm(sign=s, coefficient_bps=b, source_category_ids=c)  # type: ignore[arg-type]
            for s, b, c in terms
        )
    )


def _category(conn: sqlite3.Connection, user_id: int, name: str) -> int:
    return categories_repo.create(
        conn, user_id, NewCategory(name=name, direction=Direction.EXPENSE)
    ).id


def _formula_rule(
    conn: sqlite3.Connection,
    user_id: int,
    account_id: int,
    category_id: int,
    formula: AmountFormula,
    *,
    due: dt.date = EXPENSE_RULE_DUE,
) -> RecurringRule:
    rule = seed_rule(conn, user_id, category_id, account_id, due, amount=1)
    return recurring_repo.update_rule(
        conn, user_id, rule.id, PatchRecurringRule(amount_formula=formula)
    )


class TestParsePercentBoundaries:
    def test_upper_bound_is_inclusive(self) -> None:
        assert parse_percent_to_bps("10000") == 1_000_000

    def test_just_above_upper_bound_rejected_with_exact_message(self) -> None:
        with pytest.raises(FormulaError) as exc:
            parse_percent_to_bps("10000.01")
        assert str(exc.value) == "coefficient must be between 0.01% and 10000.00%"

    def test_below_lower_bound_message_is_exact(self) -> None:
        with pytest.raises(FormulaError) as exc:
            parse_percent_to_bps("0.004")
        assert str(exc.value) == "coefficient must be between 0.01% and 10000.00%"

    def test_half_up_on_sub_bps_tie(self) -> None:
        assert parse_percent_to_bps("0.015") == 2  # 1.5 bps -> 2
        assert parse_percent_to_bps("0.025") == 3  # 2.5 bps -> 3 (HALF_EVEN would give 2)


class TestMonthBounds:
    @pytest.mark.parametrize(
        "year, month, first, last",
        [
            (2026, 11, dt.date(2026, 11, 1), dt.date(2026, 11, 30)),
            (2026, 12, dt.date(2026, 12, 1), dt.date(2026, 12, 31)),
            (2026, 1, dt.date(2026, 1, 1), dt.date(2026, 1, 31)),
            (2024, 2, dt.date(2024, 2, 1), dt.date(2024, 2, 29)),
        ],
    )
    def test_bounds(self, year: int, month: int, first: dt.date, last: dt.date) -> None:
        assert _month_bounds(year, month) == (first, last)


class TestApplyCoefficientHalfUp:
    @pytest.mark.parametrize(
        "sum_minor, bps, expected",
        [
            (100, 1250, 13),  # 12.5% of 100 = 12.5 -> 13
            (1001, 5000, 501),  # 500.5 -> 501
            (5, 5000, 3),  # 2.5 -> 3 (HALF_EVEN would give 2)
            (1, 5000, 1),  # 0.5 -> 1
            (3, 5000, 2),  # 1.5 -> 2
            (2, 2500, 1),  # 0.5 -> 1
            (7, 2500, 2),  # 1.75 -> 2
            (9, 1000, 1),  # 0.9 -> 1
            (4, 1250, 1),  # 0.5 -> 1
        ],
    )
    def test_ties_round_up(self, sum_minor: int, bps: int, expected: int) -> None:
        assert _apply_coefficient(sum_minor, bps) == expected


class TestComputeFormulaAmount:
    def test_owner_sums_only_own_live_active_rules(
        self, conn: sqlite3.Connection, world_with_tombstones: World
    ) -> None:
        owner = world_with_tombstones.owner
        # 700 (live) + 301 (second live item); the inactive 6 000 and deleted 7 000 never count.
        seed_rule(conn, OWNER_ID, owner.category_id, owner.account_id, EXPENSE_RULE_DUE, amount=301)
        formula = _f(("+", 5000, (owner.category_id,)))
        assert compute_formula_amount(conn, OWNER_ID, formula, *NOV) == 501  # 1001 * 50% HALF_UP

    def test_terms_are_summed_with_signs(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        second = _category(conn, OWNER_ID, "second")
        seed_rule(conn, OWNER_ID, second, owner.account_id, EXPENSE_RULE_DUE, amount=1000)
        formula = _f(
            ("+", 5000, (owner.category_id,)),  # 350
            ("+", 1000, (second,)),  # 100
            ("-", 2500, (second,)),  # -250
        )
        assert compute_formula_amount(conn, OWNER_ID, formula, *NOV) == 200

    def test_second_user_rules_do_not_leak(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        world = world_with_two_users
        own = _f(("+", 10_000, (world.owner.category_id,)))
        theirs = _f(("+", 10_000, (world.other.category_id,)))
        assert compute_formula_amount(conn, OWNER_ID, own, *NOV) == expense_rule_amount(OWNER_ID)
        assert compute_formula_amount(conn, OTHER_ID, theirs, *NOV) == expense_rule_amount(OTHER_ID)
        assert compute_formula_amount(conn, OTHER_ID, own, *NOV) == 0
        assert compute_formula_amount(conn, OWNER_ID, theirs, *NOV) == 0

    def test_two_users_chained_formula_uses_own_data(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        world = world_with_two_users
        mids = {}
        for rows in (world.owner, world.other):
            mid = _category(conn, rows.user_id, "mid")
            _formula_rule(
                conn, rows.user_id, rows.account_id, mid, _f(("+", 1000, (rows.category_id,)))
            )
            mids[rows.user_id] = mid
        assert (
            compute_formula_amount(conn, OWNER_ID, _f(("+", 10_000, (mids[OWNER_ID],))), *NOV) == 70
        )
        assert (
            compute_formula_amount(conn, OTHER_ID, _f(("+", 10_000, (mids[OTHER_ID],))), *NOV)
            == 140
        )

    def test_month_without_occurrence_contributes_zero(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        late = _category(conn, OWNER_ID, "late")
        seed_rule(conn, OWNER_ID, late, owner.account_id, dt.date(2027, 3, 5), amount=900)
        formula = _f(("+", 10_000, (late,)))
        assert compute_formula_amount(conn, OWNER_ID, formula, *NOV) == 0
        assert compute_formula_amount(conn, OWNER_ID, formula, 2027, 3) == 900

    def test_formula_source_with_no_occurrence_is_zero(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        src = _category(conn, OWNER_ID, "src")
        _formula_rule(
            conn,
            OWNER_ID,
            owner.account_id,
            src,
            _f(("+", 10_000, (owner.category_id,))),
            due=dt.date(2027, 3, 5),
        )
        assert compute_formula_amount(conn, OWNER_ID, _f(("+", 10_000, (src,))), *NOV) == 0

    def test_skipped_source_item_does_not_stop_later_item(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        cat = _category(conn, OWNER_ID, "skip")
        first = seed_rule(conn, OWNER_ID, cat, owner.account_id, EXPENSE_RULE_DUE, amount=111)
        seed_rule(conn, OWNER_ID, cat, owner.account_id, EXPENSE_RULE_DUE, amount=222)
        recurring_repo.upsert_override(
            conn,
            OWNER_ID,
            NewRecurringOverride(
                rule_id=first.id, occurrence_date=EXPENSE_RULE_DUE, state=OverrideState.SKIPPED
            ),
        )
        assert compute_formula_amount(conn, OWNER_ID, _f(("+", 10_000, (cat,))), *NOV) == 222

    def test_amount_override_on_source_wins(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        recurring_repo.upsert_override(
            conn,
            OWNER_ID,
            NewRecurringOverride(
                rule_id=owner.rule_id,
                occurrence_date=EXPENSE_RULE_DUE,
                state=OverrideState.OVERRIDDEN,
                amount_override=1234,
            ),
        )
        formula = _f(("+", 10_000, (owner.category_id,)))
        assert compute_formula_amount(conn, OWNER_ID, formula, *NOV) == 1234

    def test_chained_formula_source_contributes_its_computed_amount(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        mid = _category(conn, OWNER_ID, "mid")
        _formula_rule(
            conn, OWNER_ID, owner.account_id, mid, _f(("+", 1000, (owner.category_id,)))
        )  # 10% of 700 = 70
        top = _f(("+", 5000, (mid,)))
        assert compute_formula_amount(conn, OWNER_ID, top, *NOV) == 35
        assert compute_formula_amount(conn, OWNER_ID, top, *DEC) == 35

    def test_chained_formula_source_override_replaces_computed_amount(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        mid_cat = _category(conn, OWNER_ID, "mid")
        mid = _formula_rule(
            conn, OWNER_ID, owner.account_id, mid_cat, _f(("+", 1000, (owner.category_id,)))
        )
        recurring_repo.upsert_override(
            conn,
            OWNER_ID,
            NewRecurringOverride(
                rule_id=mid.id,
                occurrence_date=EXPENSE_RULE_DUE,
                state=OverrideState.OVERRIDDEN,
                amount_override=400,
            ),
        )
        assert compute_formula_amount(conn, OWNER_ID, _f(("+", 10_000, (mid_cat,))), *NOV) == 400

    def test_cached_rule_does_not_drop_earlier_total(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        cat_a = _category(conn, OWNER_ID, "a")
        cat_b = _category(conn, OWNER_ID, "b")
        seed_rule(conn, OWNER_ID, cat_a, owner.account_id, EXPENSE_RULE_DUE, amount=100)
        seed_rule(conn, OWNER_ID, cat_b, owner.account_id, EXPENSE_RULE_DUE, amount=30)
        # Term 1 caches rule b; term 2 sums a (computed) then b (cache hit).
        formula = _f(("+", 10_000, (cat_b,)), ("+", 10_000, (cat_a, cat_b)))
        assert compute_formula_amount(conn, OWNER_ID, formula, *NOV) == 30 + 130

    def test_rule_is_not_its_own_source(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        rule = _formula_rule(
            conn,
            OWNER_ID,
            owner.account_id,
            owner.category_id,
            _f(("+", 1000, (owner.category_id,))),
        )
        assert rule.amount_formula is not None
        assert resolve_rule_amount(conn, OWNER_ID, rule, EXPENSE_RULE_DUE) == 70
        assert (
            compute_formula_amount(
                conn, OWNER_ID, rule.amount_formula, *NOV, exclude_rule_id=rule.id
            )
            == 70
        )
        # Without the exclusion the rule feeds itself: (700 + 70) * 10% = 77.
        assert compute_formula_amount(conn, OWNER_ID, rule.amount_formula, *NOV) == 77

    def test_fixed_rule_resolves_to_default_amount(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        rule = recurring_repo.find_rule(conn, OWNER_ID, owner.rule_id)
        assert rule is not None
        assert resolve_rule_amount(conn, OWNER_ID, rule, EXPENSE_RULE_DUE) == 700

    def test_cycle_message_names_rule_and_ancestors(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        cat_x = _category(conn, OWNER_ID, "x")
        cat_y = _category(conn, OWNER_ID, "y")
        rx = seed_rule(conn, OWNER_ID, cat_x, owner.account_id, EXPENSE_RULE_DUE, amount=1)
        ry = seed_rule(conn, OWNER_ID, cat_y, owner.account_id, EXPENSE_RULE_DUE, amount=1)
        fx = _f(("+", 1000, (cat_y,)))
        fy = _f(("+", 1000, (cat_x,)))
        recurring_repo.update_rule(conn, OWNER_ID, rx.id, PatchRecurringRule(amount_formula=fx))
        recurring_repo.update_rule(conn, OWNER_ID, ry.id, PatchRecurringRule(amount_formula=fy))
        with pytest.raises(FormulaCycleError) as exc:
            compute_formula_amount(conn, OWNER_ID, fx, *NOV, exclude_rule_id=rx.id)
        assert str(exc.value) == (
            f"formula cycle detected via rule {rx.id} (ancestors: {sorted([rx.id, ry.id])})"
        )


class TestRtExpand:
    def _rule(self, conn: sqlite3.Connection, world: World) -> RecurringRule:
        owner = world.owner
        return _formula_rule(
            conn,
            OWNER_ID,
            owner.account_id,
            owner.category_id,
            _f(("+", 1000, (owner.category_id,))),
        )

    def test_formula_occurrence_fields_are_carried_through(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        rule = self._rule(conn, world_with_two_users)
        occs = rt_expand(conn, OWNER_ID, rule, [], dt.date(2026, 11, 1), dt.date(2026, 12, 31))
        assert [(o.occurrence_date, o.amount) for o in occs] == [
            (dt.date(2026, 11, 15), 70),
            (dt.date(2026, 12, 15), 70),
        ]
        first = occs[0]
        assert first.rule_id == rule.id
        assert first.category_id == owner.category_id
        assert first.account_id == owner.account_id
        assert first.dest_account_id is None
        assert first.effective_date == dt.date(2026, 11, 15)
        assert first.description == rule.default_description
        assert first.is_overridden is False
        assert first.is_skipped is False

    def test_transit_destination_is_carried_through(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        rule = dataclasses.replace(
            self._rule(conn, world_with_two_users), dest_account_id=owner.account_id + 100
        )
        occs = rt_expand(conn, OWNER_ID, rule, [], dt.date(2026, 11, 1), dt.date(2026, 11, 30))
        assert occs[0].dest_account_id == owner.account_id + 100

    def test_override_wins_over_formula_amount(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        rule = self._rule(conn, world_with_two_users)
        override = recurring_repo.upsert_override(
            conn,
            OWNER_ID,
            NewRecurringOverride(
                rule_id=rule.id,
                occurrence_date=EXPENSE_RULE_DUE,
                state=OverrideState.OVERRIDDEN,
                amount_override=55,
            ),
        )
        occs = rt_expand(conn, OWNER_ID, rule, [override], EXPENSE_RULE_DUE, EXPENSE_RULE_DUE)
        assert [(o.amount, o.is_overridden) for o in occs] == [(55, True)]


class TestValidateFormulaSources:
    def _chain(self, conn: sqlite3.Connection, world: World) -> tuple[int, int, int, int]:
        """rx (fixed, cat_x) and ry (cat_y) whose formula sources cat_x."""
        owner = world.owner
        cat_x = _category(conn, OWNER_ID, "x")
        cat_y = _category(conn, OWNER_ID, "y")
        rx = seed_rule(conn, OWNER_ID, cat_x, owner.account_id, EXPENSE_RULE_DUE, amount=1)
        ry = _formula_rule(conn, OWNER_ID, owner.account_id, cat_y, _f(("+", 1000, (cat_x,))))
        return cat_x, cat_y, rx.id, ry.id

    def test_self_category_reference_rejected(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        with pytest.raises(FormulaCycleError) as exc:
            validate_formula_sources(
                conn,
                OWNER_ID,
                _f(("+", 1000, (owner.category_id,))),
                exclude_rule_id=owner.rule_id,
            )
        assert str(exc.value) == "a formula cannot reference its own category"

    def test_indirect_cycle_through_existing_formula_rejected(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        _cat_x, cat_y, rx, _ry = self._chain(conn, world_with_two_users)
        # rx (in cat_x) would now source cat_y, whose rule sources cat_x: back to rx.
        with pytest.raises(FormulaCycleError) as exc:
            validate_formula_sources(conn, OWNER_ID, _f(("+", 1000, (cat_y,))), exclude_rule_id=rx)
        assert str(exc.value) == f"formula would create a cycle via rule {rx}"

    def test_new_unsaved_rule_referencing_chain_is_accepted(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        _cat_x, cat_y, _rx, _ry = self._chain(conn, world_with_two_users)
        validate_formula_sources(conn, OWNER_ID, _f(("+", 1000, (cat_y,))))

    def test_inactive_rule_does_not_form_a_cycle(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        _cat_x, cat_y, rx, ry = self._chain(conn, world_with_two_users)
        set_inactive(conn, OWNER_ID, ry)
        validate_formula_sources(conn, OWNER_ID, _f(("+", 1000, (cat_y,))), exclude_rule_id=rx)

    def test_other_users_rules_are_not_followed(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        _cat_x, cat_y, rx, _ry = self._chain(conn, world_with_two_users)
        validate_formula_sources(conn, OTHER_ID, _f(("+", 1000, (cat_y,))), exclude_rule_id=rx)

    def test_diamond_with_cycle_behind_shared_node_is_detected(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        acct = world_with_two_users.owner.account_id
        target_cat = _category(conn, OWNER_ID, "target")
        target = seed_rule(conn, OWNER_ID, target_cat, acct, EXPENSE_RULE_DUE, amount=1)
        sink_cat = _category(conn, OWNER_ID, "sink")
        _formula_rule(conn, OWNER_ID, acct, sink_cat, _f(("+", 1000, (target_cat,))))
        shared_cat = _category(conn, OWNER_ID, "shared")
        _formula_rule(conn, OWNER_ID, acct, shared_cat, _f(("+", 1000, (sink_cat,))))
        left_cat = _category(conn, OWNER_ID, "left")
        _formula_rule(conn, OWNER_ID, acct, left_cat, _f(("+", 1000, (shared_cat,))))
        right_cat = _category(conn, OWNER_ID, "right")
        _formula_rule(conn, OWNER_ID, acct, right_cat, _f(("+", 1000, (shared_cat,))))
        with pytest.raises(FormulaCycleError) as exc:
            validate_formula_sources(
                conn,
                OWNER_ID,
                _f(("+", 1000, (left_cat, right_cat))),
                exclude_rule_id=target.id,
            )
        assert str(exc.value) == f"formula would create a cycle via rule {target.id}"

    def test_diamond_without_cycle_is_accepted(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        acct = world_with_two_users.owner.account_id
        leaf_cat = _category(conn, OWNER_ID, "leaf")
        seed_rule(conn, OWNER_ID, leaf_cat, acct, EXPENSE_RULE_DUE, amount=1)
        left_cat = _category(conn, OWNER_ID, "left")
        _formula_rule(conn, OWNER_ID, acct, left_cat, _f(("+", 1000, (leaf_cat,))))
        right_cat = _category(conn, OWNER_ID, "right")
        _formula_rule(conn, OWNER_ID, acct, right_cat, _f(("+", 1000, (leaf_cat,))))
        validate_formula_sources(conn, OWNER_ID, _f(("+", 1000, (left_cat, right_cat))))


class TestPreviewAndSavable:
    WHEN = dt.date(2026, 11, 1)

    def test_empty_terms(self, conn: sqlite3.Connection, world_with_two_users: World) -> None:
        assert preview(conn, OWNER_ID, self.WHEN, None, []) == PreviewError(
            code="empty", message="formula needs at least one term", offending_term_index=None
        )

    def test_foreign_category_is_invalid_source_with_index(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        world = world_with_two_users
        terms = [
            DraftTerm("+", "10", (world.owner.category_id,)),
            DraftTerm("+", "10", (world.other.category_id,)),
        ]
        assert preview(conn, OWNER_ID, self.WHEN, None, terms) == PreviewError(
            code="invalid_source",
            message=f"unknown or archived source category: {world.other.category_id}",
            offending_term_index=1,
        )

    def test_bad_coefficient_is_invalid_source_with_term_index(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        terms = [
            DraftTerm("+", "10", (owner.category_id,)),
            DraftTerm("+", "abc", (owner.category_id,)),
        ]
        assert preview(conn, OWNER_ID, self.WHEN, None, terms) == PreviewError(
            code="invalid_source",
            message="coefficient must be a decimal number",
            offending_term_index=1,
        )

    def test_self_reference_is_cycle(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        result = preview(
            conn, OWNER_ID, self.WHEN, owner.rule_id, [DraftTerm("+", "10", (owner.category_id,))]
        )
        assert result == PreviewError(
            code="cycle",
            message="a formula cannot reference its own category",
            offending_term_index=None,
        )

    def test_stored_runtime_cycle_is_reported_as_cycle(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        cat_x = _category(conn, OWNER_ID, "x")
        cat_y = _category(conn, OWNER_ID, "y")
        rx = seed_rule(conn, OWNER_ID, cat_x, owner.account_id, EXPENSE_RULE_DUE, amount=1)
        ry = _formula_rule(conn, OWNER_ID, owner.account_id, cat_y, _f(("+", 1000, (cat_x,))))
        # Make the stored graph cyclic behind validate's back (a legacy row).
        recurring_repo.update_rule(
            conn, OWNER_ID, rx.id, PatchRecurringRule(amount_formula=_f(("+", 1000, (cat_y,))))
        )
        result = preview(conn, OWNER_ID, self.WHEN, None, [DraftTerm("+", "10", (cat_x,))])
        assert isinstance(result, PreviewError)
        assert result.code == "cycle"
        assert result.offending_term_index is None
        assert result.message == (
            f"formula cycle detected via rule {rx.id} (ancestors: {sorted([rx.id, ry.id])})"
        )

    def test_smallest_positive_amount_is_ok(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        # 0.15% of 700 = 1.05 -> 1 minor unit.
        result = preview(
            conn, OWNER_ID, self.WHEN, None, [DraftTerm("+", "0.15", (owner.category_id,))]
        )
        assert result == PreviewOk(amount_minor=1)

    def test_zero_is_non_positive(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        # 0.01% of 700 = 0.07 -> 0.
        result = preview(
            conn, OWNER_ID, self.WHEN, None, [DraftTerm("+", "0.01", (owner.category_id,))]
        )
        assert result == PreviewError(
            code="non_positive",
            message="formula resolved to a non-positive amount",
            offending_term_index=None,
        )

    def test_savable_amount_exact_and_rejects(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        world = world_with_two_users
        own = _f(("+", 1250, (world.owner.category_id,)))
        assert compute_savable_amount(conn, OWNER_ID, own, *NOV) == 88  # 87.5 HALF_UP
        with pytest.raises(FormulaError, match="non-positive"):
            compute_savable_amount(
                conn, OWNER_ID, _f(("-", 1000, (world.owner.category_id,))), *NOV
            )
        with pytest.raises(FormulaError) as exc:
            compute_savable_amount(
                conn, OWNER_ID, _f(("+", 1000, (world.other.category_id,))), *NOV
            )
        assert str(exc.value) == f"unknown or archived source category: {world.other.category_id}"
        assert formula_svc.invalid_source_ids(conn, OWNER_ID, [(world.owner.category_id,)]) is None


class TestMessagesAndDefaults:
    def test_blank_percent_message(self) -> None:
        for blank in ("", "  ", None):
            with pytest.raises(FormulaError) as exc:
                parse_percent_to_bps(blank)  # type: ignore[arg-type]
            assert str(exc.value) == "coefficient is required for formula rules"

    def test_sign_default_and_message(self) -> None:
        assert _parse_sign("") == "+"
        assert _parse_sign(None) == "+"  # type: ignore[arg-type]
        assert _parse_sign(" - ") == "-"
        with pytest.raises(FormulaError) as exc:
            _parse_sign("x")
        assert str(exc.value) == "term sign must be '+' or '-'"

    def test_build_term_and_formula_messages(self) -> None:
        with pytest.raises(FormulaError) as exc:
            build_term(sign="+", coefficient_percent="10", source_category_ids=[])
        assert str(exc.value) == "each term needs at least one source category"
        with pytest.raises(FormulaError) as exc2:
            build_formula([])
        assert str(exc2.value) == "formula needs at least one term"


class TestSumSkipsDoNotStopTheScan:
    def test_excluded_unrelated_and_cached_rules_precede_a_counted_one(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        acct = world_with_two_users.owner.account_id
        d = dt.date
        noise_cat = _category(conn, OWNER_ID, "noise")
        seed_rule(conn, OWNER_ID, noise_cat, acct, d(2026, 11, 1), amount=9999)
        cat_f = _category(conn, OWNER_ID, "f")
        cat_b = _category(conn, OWNER_ID, "b")
        cat_a = _category(conn, OWNER_ID, "a")
        formula = _f(("+", 10_000, (cat_b,)), ("+", 10_000, (cat_f, cat_b, cat_a)))
        f_rule = _formula_rule(conn, OWNER_ID, acct, cat_f, formula, due=d(2026, 11, 2))
        seed_rule(conn, OWNER_ID, cat_b, acct, d(2026, 11, 3), amount=30)
        seed_rule(conn, OWNER_ID, cat_a, acct, d(2026, 11, 4), amount=100)
        # Scan order: noise (skipped), f (excluded), b (cached after term 1), a (counted).
        assert (
            compute_formula_amount(conn, OWNER_ID, formula, *NOV, exclude_rule_id=f_rule.id) == 160
        )


class TestValidateTraversal:
    def test_fixed_rule_popped_first_does_not_hide_a_cycle(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        acct = world_with_two_users.owner.account_id
        target_cat = _category(conn, OWNER_ID, "target")
        target = seed_rule(conn, OWNER_ID, target_cat, acct, EXPENSE_RULE_DUE, amount=1)
        chain_cat = _category(conn, OWNER_ID, "chain")  # lowest id: seeded first, popped last
        _formula_rule(conn, OWNER_ID, acct, chain_cat, _f(("+", 1000, (target_cat,))))
        fixed_cat = _category(conn, OWNER_ID, "fixed")
        seed_rule(conn, OWNER_ID, fixed_cat, acct, EXPENSE_RULE_DUE, amount=1)
        with pytest.raises(FormulaCycleError):
            validate_formula_sources(
                conn,
                OWNER_ID,
                _f(("+", 1000, (chain_cat, fixed_cat))),
                exclude_rule_id=target.id,
            )

    def test_duplicate_stack_entry_does_not_hide_a_cycle(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        acct = world_with_two_users.owner.account_id
        target_cat = _category(conn, OWNER_ID, "target")
        target = seed_rule(conn, OWNER_ID, target_cat, acct, EXPENSE_RULE_DUE, amount=1)
        needed_cat = _category(conn, OWNER_ID, "needed")
        _formula_rule(conn, OWNER_ID, acct, needed_cat, _f(("+", 1000, (target_cat,))))
        shared_cat = _category(conn, OWNER_ID, "shared")
        seed_rule(conn, OWNER_ID, shared_cat, acct, EXPENSE_RULE_DUE, amount=1)
        parent_cat = _category(conn, OWNER_ID, "parent")
        _formula_rule(conn, OWNER_ID, acct, parent_cat, _f(("+", 1000, (shared_cat,))))
        with pytest.raises(FormulaCycleError):
            validate_formula_sources(
                conn,
                OWNER_ID,
                _f(("+", 1000, (needed_cat, shared_cat, parent_cat))),
                exclude_rule_id=target.id,
            )

    def test_formula_over_a_rule_free_category_is_accepted(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        acct = world_with_two_users.owner.account_id
        empty_cat = _category(conn, OWNER_ID, "empty")
        mid_cat = _category(conn, OWNER_ID, "mid")
        _formula_rule(conn, OWNER_ID, acct, mid_cat, _f(("+", 1000, (empty_cat,))))
        validate_formula_sources(conn, OWNER_ID, _f(("+", 1000, (mid_cat,))))


class TestSavableValidates:
    def test_cycle_is_rejected_with_user_and_exclude(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        cat_x = _category(conn, OWNER_ID, "x")
        cat_y = _category(conn, OWNER_ID, "y")
        rx = seed_rule(conn, OWNER_ID, cat_x, owner.account_id, EXPENSE_RULE_DUE, amount=1)
        _formula_rule(conn, OWNER_ID, owner.account_id, cat_y, _f(("+", 1000, (cat_x,))))
        with pytest.raises(FormulaCycleError) as exc:
            compute_savable_amount(
                conn, OWNER_ID, _f(("+", 1000, (cat_y,))), *NOV, exclude_rule_id=rx.id
            )
        assert str(exc.value) == f"formula would create a cycle via rule {rx.id}"

    def test_self_category_rejected_with_exclude(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        with pytest.raises(FormulaCycleError):
            compute_savable_amount(
                conn,
                OWNER_ID,
                _f(("+", 1000, (owner.category_id,))),
                *NOV,
                exclude_rule_id=owner.rule_id,
            )

    def test_zero_and_one_boundaries(
        self, conn: sqlite3.Connection, world_with_two_users: World
    ) -> None:
        owner = world_with_two_users.owner
        with pytest.raises(FormulaError) as exc:
            compute_savable_amount(conn, OWNER_ID, _f(("+", 1, (owner.category_id,))), *NOV)
        assert str(exc.value) == "formula resolved to a non-positive amount"  # 0.07 -> 0
        assert (
            compute_savable_amount(conn, OWNER_ID, _f(("+", 15, (owner.category_id,))), *NOV) == 1
        )
