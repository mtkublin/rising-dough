"""Integration tests for formula-derived recurring amount (ADR-0047).

Covers:
- Linear-combination terms: mixed sign, multiple categories per term.
- Repository persists + hydrates v2 JSON round-trip.
- Chaining: formula source rule contributes its computed amount.
- Save-time topological cycle detection.
- Soft-consume override contract (ADR-0046) survives.
- Router dynamic-term POST shape.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner.domain.enums import Cadence, Direction, OverrideState
from budget_planner.domain.recurring import (
    AmountFormula,
    FormulaTerm,
    NewRecurringOverride,
    PatchRecurringRule,
)
from budget_planner.repositories import (
    recurring as recurring_repo,
)
from budget_planner.services import (
    recurring as recurring_svc,
    recurring_formula as formula_svc,
    upcoming as upcoming_svc,
)
from budget_planner.services._promotion import ValidationError

USER_ID = 1


def _formula(*terms: tuple[str, int, tuple[int, ...]]) -> AmountFormula:
    def _mk(sign: str, bps: int, cats: tuple[int, ...]) -> FormulaTerm:
        if sign not in {"+", "-"}:
            raise ValueError(f"bad sign: {sign!r}")
        return FormulaTerm(
            sign=sign,  # type: ignore[arg-type]
            coefficient_bps=bps,
            source_category_ids=cats,
        )

    return AmountFormula(terms=tuple(_mk(*t) for t in terms))


@pytest.fixture
def income_a(make_category: Callable[..., int]) -> int:
    return make_category(name="Salary A", direction=Direction.INCOME)


@pytest.fixture
def income_b(make_category: Callable[..., int]) -> int:
    return make_category(name="Salary B", direction=Direction.INCOME)


@pytest.fixture
def expense_deductible(make_category: Callable[..., int]) -> int:
    return make_category(name="Deductible", direction=Direction.EXPENSE)


@pytest.fixture
def expense_tax(make_category: Callable[..., int]) -> int:
    return make_category(name="Tax", direction=Direction.EXPENSE)


@pytest.fixture
def expense_surcharge(make_category: Callable[..., int]) -> int:
    return make_category(name="Surcharge", direction=Direction.EXPENSE)


@pytest.fixture
def account_id(make_account: Callable[..., int]) -> int:
    return make_account(name="Main")


class TestComputeFormulaAmount:
    def test_single_term_sums_sources(
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        account_id: int,
        income_a: int,
        income_b: int,
    ) -> None:
        make_rule(
            account_id=account_id,
            category_id=income_a,
            amount=10_000_00,
            start_date=date(2026, 1, 10),
        )
        make_rule(
            account_id=account_id,
            category_id=income_b,
            amount=5_000_00,
            start_date=date(2026, 1, 15),
        )
        formula = _formula(("+", 1200, (income_a, income_b)))  # 12 % of total income
        # 12 % of 15 000.00 = 1 800.00 → 180_000 minor
        assert formula_svc.compute_formula_amount(conn, USER_ID, formula, 2026, 1) == 180_000

    def test_multi_term_mixed_sign(
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        account_id: int,
        income_a: int,
        expense_deductible: int,
    ) -> None:
        make_rule(
            account_id=account_id,
            category_id=income_a,
            amount=10_000_00,
            start_date=date(2026, 1, 10),
        )
        make_rule(
            account_id=account_id,
            category_id=expense_deductible,
            amount=1_000_00,
            start_date=date(2026, 1, 20),
        )
        formula = _formula(
            ("+", 1200, (income_a,)),  # +12% x 10 000.00 = +1 200.00
            ("-", 4000, (expense_deductible,)),  # -40% x 1 000.00 = -400.00
        )
        # 120 000 - 40 000 = 80 000 minor
        assert formula_svc.compute_formula_amount(conn, USER_ID, formula, 2026, 1) == 80_000


class TestRepositoryRoundTrip:
    def test_v2_json_round_trip(
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        account_id: int,
        expense_tax: int,
    ) -> None:
        formula = _formula(
            ("+", 1200, (1, 2)),
            ("-", 4000, (3,)),
        )
        rule_id = make_rule(
            account_id=account_id,
            category_id=expense_tax,
            amount=0,
            amount_formula=formula,
        )
        loaded = recurring_repo.find_rule(conn, USER_ID, rule_id)
        assert loaded is not None
        assert loaded.amount_formula is not None
        assert loaded.amount_formula.schema_version == 2
        assert len(loaded.amount_formula.terms) == 2
        assert loaded.amount_formula.terms[0].sign == "+"
        assert loaded.amount_formula.terms[0].coefficient_bps == 1200
        assert loaded.amount_formula.terms[0].source_category_ids == (1, 2)
        assert loaded.amount_formula.terms[1].sign == "-"
        assert loaded.amount_formula.terms[1].coefficient_bps == 4000
        assert loaded.amount_formula.terms[1].source_category_ids == (3,)


class TestChaining:
    def test_two_level_chain(  # noqa: PLR0917
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        account_id: int,
        income_a: int,
        expense_tax: int,
        expense_surcharge: int,
    ) -> None:
        """surcharge = 10% of tax; tax = 12% of salary A. Chain must resolve."""
        make_rule(
            account_id=account_id,
            category_id=income_a,
            amount=10_000_00,
            start_date=date(2026, 1, 1),
        )
        make_rule(
            account_id=account_id,
            category_id=expense_tax,
            amount=1,
            start_date=date(2026, 1, 15),
            amount_formula=_formula(("+", 1200, (income_a,))),  # 12 % of salary
        )
        surcharge_formula = _formula(("+", 1000, (expense_tax,)))  # 10 % of tax
        # Tax resolves to 12% x 10 000.00 = 1 200.00 → 120 000 minor.
        # Surcharge = 10% x 1 200.00 = 120.00 → 12 000 minor.
        assert (
            formula_svc.compute_formula_amount(conn, USER_ID, surcharge_formula, 2026, 1) == 12_000
        )

    def test_diamond_dependency_memoised(  # noqa: PLR0917
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        account_id: int,
        income_a: int,
        expense_tax: int,
        expense_surcharge: int,
        expense_deductible: int,
    ) -> None:
        """F3 references both F1 (expense_tax) and F2 (expense_surcharge);

        both reference fixed income_a. Compute must terminate (no double-count
        risk, just memo-safe diamond).
        """
        make_rule(
            account_id=account_id,
            category_id=income_a,
            amount=10_000_00,
            start_date=date(2026, 1, 1),
        )
        make_rule(
            account_id=account_id,
            category_id=expense_tax,
            amount=1,
            start_date=date(2026, 1, 15),
            amount_formula=_formula(("+", 1200, (income_a,))),  # 1 200.00
        )
        make_rule(
            account_id=account_id,
            category_id=expense_surcharge,
            amount=1,
            start_date=date(2026, 1, 20),
            amount_formula=_formula(("+", 500, (income_a,))),  # 500.00
        )
        # F3 = tax + surcharge → 1 200.00 + 500.00 = 1 700.00 → 170 000 minor
        f3 = _formula(("+", 10_000, (expense_tax, expense_surcharge)))
        assert formula_svc.compute_formula_amount(conn, USER_ID, f3, 2026, 1) == 170_000

    def test_yearly_formula_source_contributes_only_in_payout_month(
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        account_id: int,
        income_a: int,
        expense_tax: int,
    ) -> None:
        """Yearly formula source contributes only in its canonical month.

        Regression: `_sum_category_in_month` used to recursively compute a
        formula source rule's value for every (year, month) regardless of
        the rule's canonical schedule. A yearly-cadence bonus would then
        feed its percentage into every month's parent sum, inflating a
        monthly tax formula year-round. The fix gates on
        `generate_occurrences(rule, month_start, month_end)`.
        """
        # Monthly salary → always contributes.
        make_rule(
            account_id=account_id,
            category_id=income_a,
            amount=10_000_00,
            start_date=date(2026, 1, 1),
        )
        # Yearly bonus formula living in the SAME income category. Formula
        # irrelevant for this test — just needs to be non-fixed so we hit
        # the formula branch of `_sum_category_in_month`.
        make_rule(
            account_id=account_id,
            category_id=income_a,
            amount=1,
            start_date=date(2026, 3, 15),
            amount_formula=_formula(("+", 500, (income_a,))),  # placeholder
            cadence=Cadence.YEARLY,
        )
        # 12 % tax formula over the income category.
        tax = _formula(("+", 1200, (income_a,)))

        # January: only salary → 12 % x 10 000.00 = 1 200.00 → 120 000 minor.
        assert formula_svc.compute_formula_amount(conn, USER_ID, tax, 2026, 1) == 120_000
        # February: still only salary.
        assert formula_svc.compute_formula_amount(conn, USER_ID, tax, 2026, 2) == 120_000
        # March: salary + bonus (bonus = 5 % x 10 000.00 = 500.00 → 50 000
        # minor). Tax = 12 % x (10 000.00 + 500.00) = 1 260.00 → 126 000.
        assert formula_svc.compute_formula_amount(conn, USER_ID, tax, 2026, 3) == 126_000


class TestValidateFormulaSourcesCycle:
    def test_direct_self_cycle_rejected(
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        account_id: int,
        expense_tax: int,
    ) -> None:
        tax_id = make_rule(
            account_id=account_id,
            category_id=expense_tax,
            amount=1,
            amount_formula=_formula(("+", 1000, (expense_tax,))),
        )
        new_formula = _formula(("+", 1200, (expense_tax,)))
        with pytest.raises(formula_svc.FormulaCycleError):
            formula_svc.validate_formula_sources(conn, USER_ID, new_formula, exclude_rule_id=tax_id)

    def test_indirect_cycle_rejected(
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        account_id: int,
        expense_tax: int,
        expense_surcharge: int,
    ) -> None:
        """A→B→A: tax references surcharge; new surcharge formula references tax."""
        tax_id = make_rule(
            account_id=account_id,
            category_id=expense_tax,
            amount=1,
            amount_formula=_formula(("+", 1000, (expense_surcharge,))),
        )
        surcharge_id = make_rule(
            account_id=account_id,
            category_id=expense_surcharge,
            amount=1,
            amount_formula=_formula(("+", 500, (expense_tax,))),
        )
        # Updating surcharge to reference tax would be a cycle.
        new_formula = _formula(("+", 500, (expense_tax,)))
        with pytest.raises(formula_svc.FormulaCycleError):
            formula_svc.validate_formula_sources(
                conn, USER_ID, new_formula, exclude_rule_id=surcharge_id
            )
        # Sanity: tax_id is reachable from surcharge → cycle guard trips.
        assert tax_id > 0


class TestOverrideSoftConsume:
    def test_formula_sees_override_before_and_after_consume(
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        account_id: int,
        income_a: int,
    ) -> None:
        """ADR-0046: consumed overrides stay visible to formula compute."""
        b_id = make_rule(
            account_id=account_id,
            category_id=income_a,
            amount=10_000_00,
            start_date=date(2026, 5, 1),
        )
        recurring_repo.update_rule(
            conn, USER_ID, b_id, PatchRecurringRule(next_due=date(2026, 5, 1))
        )
        recurring_repo.upsert_override(
            conn,
            USER_ID,
            NewRecurringOverride(
                rule_id=b_id,
                occurrence_date=date(2026, 5, 1),
                state=OverrideState.OVERRIDDEN,
                amount_override=12_000_00,
            ),
        )
        formula = _formula(("+", 1200, (income_a,)))

        pre = formula_svc.compute_formula_amount(conn, USER_ID, formula, 2026, 5)
        assert pre == 144_000  # 12 % x 12 000.00

        b_txn = recurring_svc.promote_recurring(conn, USER_ID, b_id, recurring_svc.PromotionEdits())
        assert b_txn.amount == 12_000_00
        assert recurring_repo.list_overrides(conn, USER_ID, b_id) == []
        historical = recurring_repo.list_overrides_all(conn, USER_ID, b_id)
        assert len(historical) == 1
        assert historical[0].promoted_to_txn_id == b_txn.id

        post = formula_svc.compute_formula_amount(conn, USER_ID, formula, 2026, 5)
        assert post == 144_000
        june = formula_svc.compute_formula_amount(conn, USER_ID, formula, 2026, 6)
        assert june == 120_000  # back to default


class TestPromoteRecurring:
    def test_promote_uses_live_formula_amount(
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        account_id: int,
        income_a: int,
        expense_tax: int,
    ) -> None:
        make_rule(
            account_id=account_id,
            category_id=income_a,
            amount=10_000_00,
            start_date=date(2026, 2, 1),
        )
        tax_id = make_rule(
            account_id=account_id,
            category_id=expense_tax,
            amount=1,
            start_date=date(2026, 2, 15),
            amount_formula=_formula(("+", 1200, (income_a,))),
        )
        txn = recurring_svc.promote_recurring(conn, USER_ID, tax_id, recurring_svc.PromotionEdits())
        assert txn.amount == 120_000  # 12 % x 10 000.00

    def test_non_positive_formula_rejected_at_promote(  # noqa: PLR0917
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        account_id: int,
        income_a: int,
        expense_deductible: int,
        expense_tax: int,
    ) -> None:
        """ADR-0047: formula resolving to ≤ 0 raises at promotion."""
        make_rule(
            account_id=account_id,
            category_id=income_a,
            amount=1_000_00,
            start_date=date(2026, 2, 1),
        )
        make_rule(
            account_id=account_id,
            category_id=expense_deductible,
            amount=5_000_00,
            start_date=date(2026, 2, 1),
        )
        tax_id = make_rule(
            account_id=account_id,
            category_id=expense_tax,
            amount=1,
            start_date=date(2026, 2, 15),
            amount_formula=_formula(
                ("+", 1200, (income_a,)),  # +120.00
                ("-", 10_000, (expense_deductible,)),  # -5 000.00
            ),
        )
        with pytest.raises(ValidationError):
            recurring_svc.promote_recurring(conn, USER_ID, tax_id, recurring_svc.PromotionEdits())

    def test_explicit_amount_bypasses_non_positive_guard(  # noqa: PLR0917
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        account_id: int,
        income_a: int,
        expense_deductible: int,
        expense_tax: int,
    ) -> None:
        make_rule(
            account_id=account_id,
            category_id=income_a,
            amount=1_000_00,
            start_date=date(2026, 2, 1),
        )
        make_rule(
            account_id=account_id,
            category_id=expense_deductible,
            amount=5_000_00,
            start_date=date(2026, 2, 1),
        )
        tax_id = make_rule(
            account_id=account_id,
            category_id=expense_tax,
            amount=1,
            start_date=date(2026, 2, 15),
            amount_formula=_formula(
                ("+", 1200, (income_a,)),
                ("-", 10_000, (expense_deductible,)),
            ),
        )
        # Explicit edit overrides the guard — user accepts responsibility.
        txn = recurring_svc.promote_recurring(
            conn, USER_ID, tax_id, recurring_svc.PromotionEdits(amount_minor=100_00)
        )
        assert txn.amount == 100_00


class TestFormulaRouter:
    def test_create_formula_rule_round_trips(
        self,
        client: TestClient,
        make_rule: Callable[..., int],
        account_id: int,
        income_a: int,
        expense_tax: int,
    ) -> None:
        make_rule(
            account_id=account_id,
            category_id=income_a,
            amount=10_000_00,
            start_date=date(2026, 3, 1),
        )
        response = client.post(
            "/recurring",
            data={
                "cadence": "monthly",
                "start_date": "2026-03-10",
                "category_id": str(expense_tax),
                "account_id": str(account_id),
                "default_amount": "",
                "default_description": "Monthly tax",
                "day_of_month": "10",
                "amount_source": "formula",
                "terms[0][sign]": "+",
                "terms[0][coefficient_percent]": "12",
                "terms[0][source_category_ids]": str(income_a),
            },
        )
        assert response.status_code == 200, response.text
        assert "formula-chip" in response.text or "data-formula-amount" in response.text

    def test_create_multi_term_formula(  # noqa: PLR0917
        self,
        client: TestClient,
        make_rule: Callable[..., int],
        account_id: int,
        income_a: int,
        expense_deductible: int,
        expense_tax: int,
    ) -> None:
        """POST with two terms: +12% income - 40% deductible."""
        make_rule(
            account_id=account_id,
            category_id=income_a,
            amount=10_000_00,
            start_date=date(2026, 3, 1),
        )
        make_rule(
            account_id=account_id,
            category_id=expense_deductible,
            amount=1_000_00,
            start_date=date(2026, 3, 1),
        )
        response = client.post(
            "/recurring",
            data={
                "cadence": "monthly",
                "start_date": "2026-03-10",
                "category_id": str(expense_tax),
                "account_id": str(account_id),
                "default_amount": "",
                "default_description": "Net tax",
                "day_of_month": "10",
                "amount_source": "formula",
                "terms[0][sign]": "+",
                "terms[0][coefficient_percent]": "12",
                "terms[0][source_category_ids]": str(income_a),
                "terms[1][sign]": "-",
                "terms[1][coefficient_percent]": "40",
                "terms[1][source_category_ids]": str(expense_deductible),
            },
        )
        assert response.status_code == 200, response.text


NOV = date(2026, 11, 1)


class TestFormulaSourceOverrides:
    """ADR-0086: formula source rules contribute effective (overridden) amounts."""

    @staticmethod
    def _override(
        conn: sqlite3.Connection,
        rule_id: int,
        amount: int | None = None,
        *,
        skip: bool = False,
    ) -> None:
        recurring_repo.upsert_override(
            conn,
            USER_ID,
            NewRecurringOverride(
                rule_id=rule_id,
                occurrence_date=NOV,
                state=OverrideState.SKIPPED if skip else OverrideState.OVERRIDDEN,
                amount_override=amount,
            ),
        )

    @staticmethod
    def _compute(conn: sqlite3.Connection, formula: AmountFormula) -> int:
        return formula_svc.compute_formula_amount(conn, USER_ID, formula, 2026, 11)

    def _setup(
        self,
        make_rule: Callable[..., int],
        account_id: int,
        base: int,
        tax: int,
    ) -> int:
        make_rule(account_id=account_id, category_id=base, amount=10_000_00, start_date=NOV)
        return make_rule(
            account_id=account_id,
            category_id=tax,
            amount=1,
            start_date=NOV,
            amount_formula=_formula(("+", 1000, (base,))),  # 10 % -> 1 000.00
        )

    def test_amount_override_on_formula_source(
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        account_id: int,
        income_a: int,
        expense_tax: int,
    ) -> None:
        tax_id = self._setup(make_rule, account_id, income_a, expense_tax)
        parent = _formula(("+", 10_000, (expense_tax,)))
        assert self._compute(conn, parent) == 1_000_00
        self._override(conn, tax_id, 700_00)
        assert self._compute(conn, parent) == 700_00

    def test_override_survives_promotion(
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        account_id: int,
        income_a: int,
        expense_tax: int,
    ) -> None:
        tax_id = self._setup(make_rule, account_id, income_a, expense_tax)
        parent = _formula(("+", 10_000, (expense_tax,)))
        self._override(conn, tax_id, 700_00)
        recurring_svc.promote_recurring(conn, USER_ID, tax_id, recurring_svc.PromotionEdits())
        assert self._compute(conn, parent) == 700_00

    def test_skipped_formula_source_contributes_zero(
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        account_id: int,
        income_a: int,
        expense_tax: int,
    ) -> None:
        tax_id = self._setup(make_rule, account_id, income_a, expense_tax)
        self._override(conn, tax_id, skip=True)
        assert self._compute(conn, _formula(("+", 10_000, (expense_tax,)))) == 0

    def test_two_formula_sources_same_category_each_overridden(
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        account_id: int,
        income_a: int,
        expense_tax: int,
    ) -> None:
        t1 = self._setup(make_rule, account_id, income_a, expense_tax)
        t2 = make_rule(
            account_id=account_id,
            category_id=expense_tax,
            amount=1,
            start_date=NOV,
            amount_formula=_formula(("+", 2000, (income_a,))),  # 2 000.00
        )
        parent = _formula(("+", 10_000, (expense_tax,)))
        assert self._compute(conn, parent) == 3_000_00
        self._override(conn, t1, 700_00)
        self._override(conn, t2, 300_00)
        assert self._compute(conn, parent) == 1_000_00

    def test_override_at_middle_of_chain(  # noqa: PLR0917
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        account_id: int,
        income_a: int,
        expense_tax: int,
        expense_surcharge: int,
    ) -> None:
        """grand = 100 % surcharge; surcharge = 50 % tax; tax = 10 % salary."""
        tax_id = self._setup(make_rule, account_id, income_a, expense_tax)
        sur_id = make_rule(
            account_id=account_id,
            category_id=expense_surcharge,
            amount=1,
            start_date=NOV,
            amount_formula=_formula(("+", 5000, (expense_tax,))),
        )
        grand = _formula(("+", 10_000, (expense_surcharge,)))
        assert self._compute(conn, grand) == 500_00
        self._override(conn, tax_id, 800_00)  # flows into surcharge computation
        assert self._compute(conn, grand) == 400_00
        self._override(conn, sur_id, 123_00)  # middle-level override wins
        assert self._compute(conn, grand) == 123_00

    def test_cycle_guard_still_raises(
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        account_id: int,
        expense_tax: int,
        expense_surcharge: int,
    ) -> None:
        a = make_rule(
            account_id=account_id,
            category_id=expense_tax,
            amount=1,
            start_date=NOV,
            amount_formula=_formula(("+", 1000, (expense_surcharge,))),
        )
        make_rule(
            account_id=account_id,
            category_id=expense_surcharge,
            amount=1,
            start_date=NOV,
            amount_formula=_formula(("+", 1000, (expense_tax,))),
        )
        self._override(conn, a, 5_00)
        with pytest.raises(formula_svc.FormulaCycleError):
            self._compute(conn, _formula(("+", 10_000, (expense_tax,))))

    def test_user_shape_regression_and_surface_parity(
        self,
        conn: sqlite3.Connection,
        make_rule: Callable[..., int],
        make_category: Callable[..., int],
        account_id: int,
    ) -> None:
        base = make_category(name="Base", direction=Direction.INCOME)
        wyplata = make_category(name="Wyplata", direction=Direction.INCOME)
        vat = make_category(name="Wyplata VAT", direction=Direction.INCOME)
        podatki = make_category(name="Podatki", direction=Direction.EXPENSE)
        osobiste = make_category(name="Osobiste", direction=Direction.EXPENSE)

        def mk(cat: int, amt: int, f: AmountFormula | None = None) -> int:
            return make_rule(
                account_id=account_id,
                category_id=cat,
                amount=amt,
                start_date=NOV,
                amount_formula=f,
            )

        mk(base, 4_000_00)
        w = mk(wyplata, 10_000_00)  # fixed
        wv = mk(vat, 1, _formula(("+", 5000, (base,))))  # formula, not chained
        p1 = mk(podatki, 1, _formula(("+", 1000, (wyplata,)), ("+", 1000, (vat,))))  # chained
        p2 = mk(podatki, 1, _formula(("+", 2000, (vat,))))  # chained
        parent_formula = _formula(
            ("+", 10_000, (wyplata,)),
            ("+", 10_000, (vat,)),
            ("-", 10_000, (podatki,)),
        )
        parent = mk(osobiste, 1, parent_formula)

        for rid, amt in ((w, 12_000_00), (wv, 6_000_00), (p1, 700_00), (p2, 300_00)):
            self._override(conn, rid, amt)
        for rid in (w, wv):
            recurring_svc.promote_recurring(conn, USER_ID, rid, recurring_svc.PromotionEdits())

        expected = (12_000 + 6_000 - 700 - 300) * 100
        assert self._compute(conn, parent_formula) == expected

        rule = recurring_repo.find_rule(conn, USER_ID, parent)
        assert rule is not None
        assert formula_svc.resolve_rule_amount(conn, USER_ID, rule, NOV) == expected
        occs = formula_svc.rt_expand(
            conn,
            USER_ID,
            rule,
            recurring_repo.list_overrides_all(conn, USER_ID, parent),
            NOV,
            date(2026, 11, 30),
        )
        assert [o.amount for o in occs] == [expected]
        # Upcoming resolves the amount through the same entry point.
        item = next(
            i
            for i in upcoming_svc.list_upcoming(conn, USER_ID, today=NOV, window_days=None)
            if i.rule_id == parent
        )
        assert item.amount_minor == formula_svc.resolve_rule_amount(
            conn, USER_ID, rule, item.effective_date
        )
