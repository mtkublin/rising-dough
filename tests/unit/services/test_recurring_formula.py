"""Unit tests for formula-derived recurring amounts (ADR-0047)."""

from __future__ import annotations

import datetime as dt

import pytest

from budget_planner.domain.enums import Cadence
from budget_planner.domain.recurring import (
    FORMULA_SCHEMA_VERSION,
    AmountFormula,
    FormulaTerm,
    RecurringRule,
)
from budget_planner.services.recurring_formula import (
    FormulaError,
    _apply_coefficient,
    _collect_referenced_category_ids,
    build_formula,
    build_term,
    parse_percent_to_bps,
)


class TestParsePercentToBps:
    @pytest.mark.parametrize(
        "percent_str, expected_bps",
        [
            ("12", 1200),
            ("12.5", 1250),
            ("0.01", 1),
            ("0,01", 1),
            ("100", 10_000),
            ("12.345", 1234),  # sub-bps tie -> even (T-Q281; was 1235)
        ],
    )
    def test_valid_inputs(self, percent_str: str, expected_bps: int) -> None:
        assert parse_percent_to_bps(percent_str) == expected_bps

    @pytest.mark.parametrize("bad", ["", "   ", "abc", "12%", "--1"])
    def test_rejects_bad_decimals(self, bad: str) -> None:
        with pytest.raises(FormulaError):
            parse_percent_to_bps(bad)

    @pytest.mark.parametrize("bad", ["0", "-5", "0.001", "10001"])
    def test_rejects_out_of_range(self, bad: str) -> None:
        with pytest.raises(FormulaError):
            parse_percent_to_bps(bad)


class TestBuildTerm:
    def test_default_sign_plus(self) -> None:
        term = build_term(sign="+", coefficient_percent="12", source_category_ids=[5])
        assert term.sign == "+"
        assert term.coefficient_bps == 1200
        assert term.source_category_ids == (5,)

    def test_negative_sign(self) -> None:
        term = build_term(sign="-", coefficient_percent="40", source_category_ids=[11])
        assert term.sign == "-"

    def test_invalid_sign_rejected(self) -> None:
        with pytest.raises(FormulaError):
            build_term(sign="*", coefficient_percent="12", source_category_ids=[5])

    def test_dedupes_category_ids(self) -> None:
        term = build_term(sign="+", coefficient_percent="12", source_category_ids=[5, 7, 5, 9, 7])
        assert term.source_category_ids == (5, 7, 9)

    def test_empty_category_list_rejected(self) -> None:
        with pytest.raises(FormulaError):
            build_term(sign="+", coefficient_percent="12", source_category_ids=[])


class TestBuildFormula:
    def test_wraps_terms(self) -> None:
        term = FormulaTerm(sign="+", coefficient_bps=1200, source_category_ids=(5,))
        formula = build_formula([term])
        assert isinstance(formula, AmountFormula)
        assert formula.schema_version == FORMULA_SCHEMA_VERSION
        assert formula.terms == (term,)

    def test_empty_terms_rejected(self) -> None:
        with pytest.raises(FormulaError):
            build_formula([])


class TestApplyCoefficient:
    @pytest.mark.parametrize(
        "sum_minor, bps, expected",
        [
            (10_000_00, 1200, 120_000),  # 12% of 10 000.00 = 1 200.00 → 120000 minor
            (0, 1200, 0),
            (100, 1, 0),  # 0.01% of 1.00 = 0.0001 → 0
            (10_001_00, 1, 100),  # 0.01% of 10 001.00 = 1.0001 → 100 minor
            (12_34, 1050, 130),  # 12.34 * 10.5% = 1.2957 (no tie) → 1.30
        ],
    )
    def test_rounding(self, sum_minor: int, bps: int, expected: int) -> None:
        assert _apply_coefficient(sum_minor, bps) == expected


class TestCollectReferencedCategoryIds:
    def test_flattens_across_terms(self) -> None:
        formula = AmountFormula(
            terms=(
                FormulaTerm(sign="+", coefficient_bps=1200, source_category_ids=(5, 7)),
                FormulaTerm(sign="-", coefficient_bps=4000, source_category_ids=(11,)),
            ),
        )
        assert _collect_referenced_category_ids(formula) == {5, 7, 11}


def _mk_rule(
    *,
    rule_id: int,
    category_id: int,
    amount: int,
    cadence_value: str = "monthly",
    start_date: dt.date = dt.date(2026, 1, 1),
    next_due: dt.date = dt.date(2026, 1, 1),
    formula: AmountFormula | None = None,
) -> object:
    now = dt.datetime.now(dt.UTC)
    return RecurringRule(
        id=rule_id,
        user_id=1,
        cadence=Cadence(cadence_value),
        start_date=start_date,
        end_date=None,
        category_id=category_id,
        account_id=1,
        dest_account_id=None,
        default_amount=amount,
        default_description="",
        day_of_month=None,
        month_of_year=None,
        active=True,
        next_due=next_due,
        last_promoted_date=None,
        created_at=now,
        updated_at=now,
        deleted_at=None,
        amount_formula=formula,
    )
