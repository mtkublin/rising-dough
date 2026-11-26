"""Bad dialog input is a 422 with a visible field error, never a 500 and never stored (T-UR47).

Requirement F1.1a. Each case asserts the status, the field error line, the typed value kept,
the stored rows and the audit count unchanged, and that a second user's rule is untouched.
"""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.budgets import NewBudgetDefault
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.repositories import (
    accounts as accounts_repo,
    budgets as budgets_repo,
    categories as categories_repo,
    recurring as recurring_repo,
)
from tests.contract.test_plan_support import audit_total
from tests.ui_map import _html
from tests.ui_map.locator import by_id

pytest_plugins = ("tests.integration.web.test_recurring_dialogs",)

USER_ID = 1
HX = {"HX-Request": "true", "HX-Target": "modal-root"}
DAY_ERROR = "▲ day of month must be 1 to 31"


def _rule_form(ids: dict[str, int], **extra: str) -> dict[str, str]:
    return {
        "category": str(ids["rent"]),
        "account_id": str(ids["acc"]),
        "amount_source": "fixed",
        "default_amount": "321.50",
        "default_description": "typed note",
        "start_date": "2026-01-01",
        "cadence": "monthly",
        **extra,
    }


def _other_users_rule(db: sqlite3.Connection) -> int:
    db.execute("INSERT INTO users(id, name) VALUES (2, 'other')")
    acc = accounts_repo.create(db, 2, NewAccount(name="Theirs", currency="PLN"))
    cat = categories_repo.create(db, 2, NewCategory(name="Rent", direction=Direction.EXPENSE))
    return recurring_repo.create_rule(
        db,
        2,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 1, 1),
            category_id=cat.id,
            account_id=acc.id,
            default_amount=1,
        ),
    ).id


def _day(db: sqlite3.Connection, rule_id: int) -> int | None:
    row = db.execute("SELECT day_of_month FROM recurring_rules WHERE id = ?", (rule_id,)).fetchone()
    return None if row is None else row[0]


@pytest.mark.parametrize("day", ["45", "0", "32", "abc", "-3"])
def test_edit_recurring_bad_day_of_month_is_a_422_and_stores_nothing(
    client: TestClient,
    db: sqlite3.Connection,
    ids: dict[str, int],
    day: str,
) -> None:
    theirs = _other_users_rule(db)
    audit = audit_total(db)
    amount_before = recurring_repo.find_rule(db, USER_ID, ids["rent_rule"])
    assert amount_before is not None

    r = client.post(
        f"/recurring/{ids['rent_rule']}", data=_rule_form(ids, day_of_month=day), headers=HX
    )

    assert r.status_code == 422
    assert _html.error_lines(r.text) == {"field-day_of_month-error": DAY_ERROR}
    assert _html.resolve_one(r.text, by_id("field-day_of_month"))["value"] == day
    stored = recurring_repo.find_rule(db, USER_ID, ids["rent_rule"])
    assert stored == amount_before
    assert _day(db, ids["rent_rule"]) is None
    assert audit_total(db) == audit
    assert _day(db, theirs) is None


def test_edit_recurring_good_day_of_month_is_stored(
    client: TestClient,
    db: sqlite3.Connection,
    ids: dict[str, int],
) -> None:
    theirs = _other_users_rule(db)

    r = client.post(
        f"/recurring/{ids['rent_rule']}", data=_rule_form(ids, day_of_month="31"), headers=HX
    )

    assert r.status_code == 200
    assert _day(db, ids["rent_rule"]) == 31
    stored = recurring_repo.find_rule(db, USER_ID, ids["rent_rule"])
    assert stored is not None
    assert stored.default_amount == 32_150
    assert _day(db, theirs) is None


@pytest.mark.parametrize("day", ["45", "abc"])
def test_new_recurring_bad_day_of_month_is_a_422_and_creates_nothing(
    client: TestClient,
    db: sqlite3.Connection,
    ids: dict[str, int],
    day: str,
) -> None:
    audit = audit_total(db)
    rules = db.execute("SELECT COUNT(*) FROM recurring_rules").fetchone()[0]

    r = client.post("/recurring", data=_rule_form(ids, day_of_month=day), headers=HX)

    assert r.status_code == 422
    assert _html.error_lines(r.text) == {"field-day_of_month-error": DAY_ERROR}
    assert db.execute("SELECT COUNT(*) FROM recurring_rules").fetchone()[0] == rules
    assert audit_total(db) == audit


@pytest.mark.parametrize("year", ["0", "1899", "10000", "99999", "-1"])
def test_one_off_override_bad_year_is_a_422_and_stores_nothing(
    client: TestClient,
    db: sqlite3.Connection,
    ids: dict[str, int],
    year: str,
) -> None:
    audit = audit_total(db)

    r = client.post(
        f"/budget/rules/{ids['rent']}/overrides",
        data={"tier": "one-off", "year": year, "month": "3", "amount": "5"},
        headers=HX,
    )

    assert r.status_code == 422
    assert _html.error_lines(r.text) == {"dialog-error-year": "▲ Year: enter a year"}
    assert budgets_repo.list_one_off(db, USER_ID) == []
    assert audit_total(db) == audit


@pytest.mark.parametrize("year", ["0", "99999"])
def test_one_off_route_bad_year_is_a_422_and_stores_nothing(
    client: TestClient,
    db: sqlite3.Connection,
    ids: dict[str, int],
    year: str,
) -> None:
    audit = audit_total(db)

    r = client.post(f"/budget/one-off/{ids['rent']}/{year}/3", data={"amount": "5"}, headers=HX)

    assert r.status_code == 422
    assert budgets_repo.list_one_off(db, USER_ID) == []
    assert audit_total(db) == audit


@pytest.mark.parametrize("amount", ["", "  ", "abc"])
def test_override_empty_or_text_amount_is_a_422_and_the_default_is_kept(
    client: TestClient,
    db: sqlite3.Connection,
    ids: dict[str, int],
    amount: str,
) -> None:
    budgets_repo.set_default(db, USER_ID, NewBudgetDefault(category_id=ids["rent"], amount=50_000))
    audit = audit_total(db)

    for tier in ("one-off", "recurring", "default"):
        r = client.post(
            f"/budget/rules/{ids['rent']}/overrides",
            data={"tier": tier, "year": "2026", "month": "3", "amount": amount},
            headers=HX,
        )
        assert r.status_code == 422
        assert _html.error_lines(r.text) == {"field-amount-error": "▲ enter an amount of 0 or more"}

    default = budgets_repo.get_default(db, USER_ID, ids["rent"])
    assert default is not None
    assert default.amount == 50_000
    assert budgets_repo.list_one_off(db, USER_ID) == []
    assert budgets_repo.list_recurring(db, USER_ID) == []
    assert audit_total(db) == audit


def test_new_account_bad_opening_balance_is_a_422_and_creates_nothing(
    client: TestClient,
    db: sqlite3.Connection,
    ids: dict[str, int],
) -> None:
    accounts = db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    audit = audit_total(db)

    r = client.post(
        "/accounts",
        data={"name": "Typed", "currency": "PLN", "opening_balance": "abc", "type": "cash"},
        headers=HX,
    )

    assert r.status_code == 422
    assert _html.resolve_one(r.text, by_id("field-name"))["value"] == "Typed"
    assert _html.resolve_one(r.text, by_id("field-opening_balance"))["value"] == "abc"
    assert list(_html.error_lines(r.text)) == ["field-opening_balance-error"]
    assert db.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == accounts
    assert audit_total(db) == audit


def test_duplicate_category_name_is_a_422_on_create_and_rename(
    client: TestClient,
    db: sqlite3.Connection,
    ids: dict[str, int],
) -> None:
    audit = audit_total(db)
    count = db.execute("SELECT COUNT(*) FROM categories").fetchone()[0]

    created = client.post("/categories", data={"name": "Rent", "direction": "expense"}, headers=HX)
    renamed = client.post(f"/categories/{ids['taxes']}", data={"name": "Rent"}, headers=HX)

    for r in (created, renamed):
        assert r.status_code == 422
        assert list(_html.error_lines(r.text)) == ["field-name-error"]
    assert db.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == count
    taxes = categories_repo.find_by_id(db, USER_ID, ids["taxes"])
    assert taxes is not None
    assert taxes.name == "Taxes"
    assert audit_total(db) == audit


@pytest.mark.parametrize("amount", ["", "abc", "0"])
def test_empty_or_bad_amount_uses_the_q24_copy(
    client: TestClient,
    db: sqlite3.Connection,
    ids: dict[str, int],
    amount: str,
) -> None:
    r = client.post(
        f"/recurring/{ids['rent_rule']}",
        data=_rule_form(ids, default_amount=amount),
        headers=HX,
    )

    assert r.status_code == 422
    assert _html.error_lines(r.text)["field-default_amount-error"] == "▲ Enter an amount above 0.00"
    stored = recurring_repo.find_rule(db, USER_ID, ids["rent_rule"])
    assert stored is not None
    assert stored.default_amount == 50_000
