"""Form parsers moved out of the routers (T-Q266): exact commands and exact error messages."""

from __future__ import annotations

import sqlite3
from datetime import date

from starlette.datastructures import FormData

from budget_planner.domain.accounts import Account, NewAccount, PatchAccount
from budget_planner.domain.budgets import (
    NewBudgetDefault,
    NewBudgetOneOffOverride,
    NewBudgetRecurringOverride,
)
from budget_planner.domain.categories import NewCategory, PatchCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.repositories import accounts
from budget_planner.services.category_forms import parse_category_patch, parse_new_category
from budget_planner.web.account_forms import (
    parse_account_patch,
    parse_category_id,
    parse_liability,
    parse_new_account,
    parse_save_snapshot,
)
from budget_planner.web.budget_forms import parse_override
from budget_planner.web.recurring_forms import (
    parse_terms_from_form,
    resolve_amount_inputs,
    validate_cadence,
)
from tests.formula_fx_support import formula_fx_of

# --- categories -------------------------------------------------------------------------------


def test_new_category_parses_income_with_trimmed_name_and_colour() -> None:
    parsed = parse_new_category(
        name="  Pay  ", direction="income", color="#AABBCC", clear_color=None
    )

    assert parsed.errors == {}
    assert parsed.command == NewCategory(name="Pay", direction=Direction.INCOME, color="#aabbcc")


def test_new_category_rejects_system_directions_and_reports_every_error() -> None:
    parsed = parse_new_category(name="", direction="transit", color="nope", clear_color=None)

    assert parsed.command is None
    assert set(parsed.errors) == {"direction", "name", "color"}
    assert parsed.errors["direction"] == "invalid direction"


def test_category_patch_clear_color_wins_over_posted_colour() -> None:
    parsed = parse_category_patch(name="Food", color="#112233", clear_color="1")

    assert parsed.patch == PatchCategory(name="Food", color=None, clear_color=True)


# --- accounts ---------------------------------------------------------------------------------


def test_new_account_liability_needs_a_positive_credit_limit() -> None:
    parsed = parse_new_account(
        name="Card",
        currency="pln",
        opening_balance="0",
        account_type="",
        is_liability="on",
        credit_limit="",
    )

    assert parsed.command is None
    assert parsed.errors == {"credit_limit": "positive credit limit required"}


def test_new_account_builds_minor_units_and_uppercases_currency() -> None:
    parsed = parse_new_account(
        name=" Wallet ",
        currency=" eur ",
        opening_balance="12.34",
        account_type="cash",
        is_liability="",
        credit_limit="",
    )

    assert parsed.errors == {}
    assert parsed.command == NewAccount(
        name="Wallet",
        currency="EUR",
        opening_balance=1234,
        type="cash",
        is_liability=False,
        credit_limit_minor=None,
    )


def test_new_account_reports_bad_currency_and_amount_without_a_limit_error() -> None:
    parsed = parse_new_account(
        name="x",
        currency="PL1",
        opening_balance="abc",
        account_type="",
        is_liability="true",
        credit_limit="",
    )

    assert parsed.errors == {
        "currency": "ISO 4217 code required",
        "opening_balance": "invalid number",
    }


def _account(conn: sqlite3.Connection) -> Account:
    return accounts.create(conn, 1, NewAccount(name="A", currency="PLN", opening_balance=0))


def test_checkbox_and_id_parsers() -> None:
    assert [parse_liability(v) for v in ("on", " TRUE ", "1", "", "no")] == [
        True,
        True,
        True,
        False,
        False,
    ]
    assert [parse_save_snapshot(v) for v in ("yes", "on", "0", "")] == [True, True, False, False]
    assert [parse_category_id(v) for v in ("12", " 7 ", "", "x")] == [12, 7, None, None]


def test_account_patch_clears_limit_for_non_liability(conn: sqlite3.Connection) -> None:
    parsed = parse_account_patch(
        _account(conn), name="Main", account_type="", is_liability="", credit_limit="99"
    )

    assert parsed.patch == PatchAccount(
        name="Main",
        type=None,
        is_liability=False,
        credit_limit_minor=None,
        clear_credit_limit=True,
    )


# --- budget -----------------------------------------------------------------------------------


def _override(**kw: str) -> tuple[object, str | None]:
    base = {"tier": "default", "month": "", "year": "", "amount": "10", "currency": "PLN"}
    parsed = parse_override(5, **{**base, **kw})
    return parsed.command, parsed.error


def test_override_default_blank_amount_is_zero() -> None:
    assert _override(amount="") == (NewBudgetDefault(category_id=5, amount=0), None)


def test_override_recurring_and_one_off_commands() -> None:
    assert _override(tier="recurring", month="3") == (
        NewBudgetRecurringOverride(category_id=5, month=3, amount=1000),
        None,
    )
    assert _override(tier="one-off", month="12", year="2026", amount="1,5") == (
        NewBudgetOneOffOverride(category_id=5, year=2026, month=12, amount=150),
        None,
    )


def test_override_errors_in_original_order() -> None:
    assert _override(tier="weekly") == (None, "invalid tier")
    assert _override(amount="-1") == (None, "invalid amount")
    assert _override(tier="recurring", month="13") == (None, "invalid month")
    assert _override(tier="one-off", month="2", year="x") == (None, "invalid year")
    assert _override(tier="one-off", month="14", year="x") == (None, "invalid month")


# --- recurring --------------------------------------------------------------------------------


def test_terms_are_grouped_by_index_and_holes_collapse() -> None:
    form = FormData(
        [
            ("terms[2][sign]", "-"),
            ("terms[2][coefficient_percent]", "25"),
            ("terms[0][source_category_ids]", "4"),
            ("terms[0][source_category_ids]", "5"),
            ("other", "x"),
        ]
    )

    assert parse_terms_from_form(form) == [
        {"sign": "+", "coefficient_percent": "", "source_category_ids": ("4", "5")},
        {"sign": "-", "coefficient_percent": "25", "source_category_ids": ()},
    ]


def test_cadence_lookup() -> None:
    assert validate_cadence("monthly") is Cadence.MONTHLY
    assert validate_cadence("hourly") is None


def _amounts(
    conn: sqlite3.Connection, *, source: str, amount: str, currency: str | None
) -> tuple[int | None, object, dict[str, str]]:
    return resolve_amount_inputs(
        conn,
        1,
        amount_source=source,
        default_amount=amount,
        term_inputs=[],
        account_currency=currency,
        exclude_rule_id=None,
        today=date(2026, 1, 1),
        fx=formula_fx_of(conn, 1),
    )


def test_fixed_amount_needs_an_account_currency_and_a_positive_amount(
    conn: sqlite3.Connection,
) -> None:
    assert _amounts(conn, source="fixed", amount="12.50", currency="PLN") == (1250, None, {})
    assert _amounts(conn, source="fixed", amount="1", currency=None) == (
        None,
        None,
        {"default_amount": "unknown account currency"},
    )
    assert _amounts(conn, source="formula", amount="1", currency=None) == (
        None,
        None,
        {"amount_source": "unknown account currency"},
    )
    assert _amounts(conn, source="fixed", amount="-3", currency="PLN") == (
        None,
        None,
        {"default_amount": "amount must be positive"},
    )
