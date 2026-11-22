"""T-Q215 — formula source sums convert across currencies (ADR-0006, ADR-0139)."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import pytest

from budget_planner.domain.enums import Direction
from budget_planner.domain.recurring import AmountFormula, FormulaTerm
from budget_planner.repositories import fx as fx_repo
from budget_planner.services import fx, recurring_formula as formula_svc
from budget_planner.services.fx import FxUnavailableError

USER_ID = 1
TODAY = date(2026, 11, 22)


def _ctx(conn: sqlite3.Connection, base: str = "PLN") -> formula_svc.FormulaFx:
    return formula_svc.FormulaFx(
        fx.build_converter(base, TODAY, _rates(conn)),
        fx.currency_by_account(conn, USER_ID, include_deleted=True),
    )


def _rates(conn: sqlite3.Connection) -> list[tuple[str, date, Decimal]]:
    return [(r.from_ccy, r.date, r.rate) for r in fx_repo.list_rates_to(conn, "PLN")]


def test_eur_source_converts_into_pln_formula_rule(
    conn: sqlite3.Connection,
    make_account: Callable[..., int],
    make_category: Callable[..., int],
    make_rule: Callable[..., int],
    make_fx_rate: Callable[..., None],
) -> None:
    pln = make_account(name="Main", currency="PLN")
    eur = make_account(name="Euro", currency="EUR")
    src = make_category(name="Salary", direction=Direction.INCOME)
    make_rule(account_id=eur, category_id=src, amount=10_000, start_date=date(2026, 11, 1))
    make_fx_rate(on_date=date(2026, 11, 1), rate="4.30")
    formula = AmountFormula(
        terms=(FormulaTerm(sign="+", coefficient_bps=10_000, source_category_ids=(src,)),)
    )

    to_pln = formula_svc.compute_formula_amount(
        conn, USER_ID, formula, 2026, 11, fx=_ctx(conn), target_ccy="PLN"
    )
    same_ccy = formula_svc.compute_formula_amount(
        conn, USER_ID, formula, 2026, 11, fx=_ctx(conn), target_ccy="EUR"
    )
    assert pln != eur
    assert to_pln == 43_000
    assert same_ccy == 10_000


def test_eur_source_into_eur_rule_with_pln_source_uses_inverse_rate(
    conn: sqlite3.Connection,
    make_account: Callable[..., int],
    make_category: Callable[..., int],
    make_rule: Callable[..., int],
    make_fx_rate: Callable[..., None],
) -> None:
    pln = make_account(name="Main", currency="PLN")
    src = make_category(name="Salary", direction=Direction.INCOME)
    make_rule(account_id=pln, category_id=src, amount=43_000, start_date=date(2026, 11, 1))
    make_fx_rate(on_date=date(2026, 11, 1), rate="4.30")
    formula = AmountFormula(
        terms=(FormulaTerm(sign="+", coefficient_bps=10_000, source_category_ids=(src,)),)
    )

    got = formula_svc.compute_formula_amount(
        conn, USER_ID, formula, 2026, 11, fx=_ctx(conn), target_ccy="EUR"
    )

    assert got == 10_000


def test_missing_rate_raises_fx_unavailable(
    conn: sqlite3.Connection,
    make_account: Callable[..., int],
    make_category: Callable[..., int],
    make_rule: Callable[..., int],
) -> None:
    eur = make_account(name="Euro", currency="EUR")
    src = make_category(name="Salary", direction=Direction.INCOME)
    make_rule(account_id=eur, category_id=src, amount=10_000, start_date=date(2026, 11, 1))
    formula = AmountFormula(
        terms=(FormulaTerm(sign="+", coefficient_bps=10_000, source_category_ids=(src,)),)
    )

    with pytest.raises(FxUnavailableError):
        formula_svc.compute_formula_amount(
            conn, USER_ID, formula, 2026, 11, fx=_ctx(conn), target_ccy="PLN"
        )
