"""T-Q256 — credit_utilisation view-model values (Q-070)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from budget_planner.domain.accounts import Account
from budget_planner.web.accounts_view import (
    AccountDialog,
    CreditUtilisation,
    account_dialog,
    checked_label,
    credit_utilisation,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _acc(*, limit: int | None, liability: bool = True) -> Account:
    return Account(
        id=1,
        user_id=1,
        name="Visa",
        type=None,
        currency="PLN",
        opening_balance=0,
        is_liability=liability,
        credit_limit_minor=limit,
        created_at=_NOW,
        updated_at=_NOW,
        deleted_at=None,
    )


def test_partial_use_exact_values() -> None:
    util = credit_utilisation(_acc(limit=500_000), -123_456)
    assert util == CreditUtilisation(
        limit_minor=500_000,
        used_minor=123_456,
        available_minor=376_544,
        over_limit_minor=0,
        used_pct=24,
        bar_pct=24,
    )


def test_over_limit_caps_bar_and_reports_excess() -> None:
    util = credit_utilisation(_acc(limit=100_000), -150_000)
    assert util is not None
    assert (util.used_minor, util.available_minor, util.over_limit_minor) == (
        150_000,
        0,
        50_000,
    )
    assert (util.used_pct, util.bar_pct) == (150, 100)


def test_positive_balance_means_nothing_used() -> None:
    util = credit_utilisation(_acc(limit=100_000), 25_000)
    assert util is not None
    assert (util.used_minor, util.available_minor, util.used_pct) == (0, 100_000, 0)


@pytest.mark.parametrize("limit", [0, None, -5])
def test_zero_or_missing_limit_has_no_utilisation(limit: int | None) -> None:
    assert credit_utilisation(_acc(limit=limit), -10_000) is None


def test_non_liability_has_no_utilisation() -> None:
    assert credit_utilisation(_acc(limit=100_000, liability=False), -10_000) is None


# --- F4b: checked label, new-account chip and as-of, credit limit visibility -----------


def test_checked_label_is_the_day_of_the_newest_signal() -> None:
    assert checked_label(datetime(2026, 10, 29, tzinfo=UTC)) == "29 OCT"
    assert checked_label(None) == "never"


def _new(**entered: str) -> AccountDialog:
    return account_dialog(None, values=entered, base_currency="PLN", today=date(2026, 10, 31))


def test_new_dialog_chip_follows_a_known_code_and_keeps_base_for_an_unknown_one() -> None:
    assert (_new().hero or {})["currency"] == "PLN"
    assert (_new(currency="eur").hero or {})["currency"] == "EUR"
    assert (_new(currency="XYZ").hero or {})["currency"] == "PLN"


def test_new_dialog_is_as_of_today_and_the_edit_dialog_has_no_date() -> None:
    assert _new().as_of == "2026-10-31"
    edit = account_dialog(_acc(limit=None), base_currency="PLN", today=date(2026, 10, 31))
    assert edit.as_of == ""


def test_edit_dialog_hint_counts_transactions_even_when_there_are_none() -> None:
    edit = account_dialog(
        _acc(limit=None, liability=False), base_currency="PLN", today=date(2026, 10, 31)
    )
    assert edit.liability_hint == "▲ 0 transactions: this balance will count against net worth."


@pytest.mark.parametrize("stored", ["credit_card", "credit card", "bank", "savings"])
def test_edit_type_select_has_one_selected_option_equal_to_the_stored_type(stored: str) -> None:
    acc = replace(_acc(limit=None, liability=False), type=stored)
    dlg = account_dialog(acc, base_currency="PLN", today=date(2026, 10, 31))
    selected = [o for o in dlg.type_options if o.selected]
    assert [o.value for o in selected] == [stored]  # saving posts the stored value back
    labels = [o.label for o in dlg.type_options]
    assert len(labels) == len(set(labels))
