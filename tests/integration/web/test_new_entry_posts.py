"""Posts of the new-entry dialog (T-UR07b, ADR-0107, ADR-0152).

The dialog posts the picker's ``category`` (the name the vendored combobox.js owns) and the
formula's ``components[i][...]`` names; the routes read them next to the legacy ``category_id`` and
``terms[i][...]``. A failed post from the dialog (``HX-Target: modal-root``) re-renders the dialog
with the posted values.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    recurring as recurring_repo,
)
from tests.ui_map import _html, entries

USER_ID = 1
FROM_DIALOG = {"HX-Request": "true", "HX-Target": "modal-root"}


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def ids(db: sqlite3.Connection) -> dict[str, int]:
    acc = accounts_repo.create(db, USER_ID, NewAccount(name="Main", currency="PLN"))
    groc = categories_repo.create(
        db, USER_ID, NewCategory(name="Groceries", direction=Direction.EXPENSE)
    )
    salary = categories_repo.create(
        db, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    )
    tax = categories_repo.create(db, USER_ID, NewCategory(name="Tax", direction=Direction.EXPENSE))
    recurring_repo.create_rule(
        db,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 3, 1),
            category_id=salary.id,
            account_id=acc.id,
            default_amount=10_000_00,
        ),
    )
    return {"acc": acc.id, "groc": groc.id, "salary": salary.id, "tax": tax.id}


def _txn(db: sqlite3.Connection) -> tuple[int, int, int, str]:
    row = db.execute(
        "SELECT id, amount, category_id, description FROM transactions ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return (row[0], row[1], row[2], row[3])


def _ops(db: sqlite3.Connection, entity: str, entity_id: int) -> list[str]:
    rows = db.execute(
        "SELECT operation FROM audit_log WHERE entity_type = ? AND entity_id = ? ORDER BY id",
        (entity, entity_id),
    ).fetchall()
    return [r[0] for r in rows]


def test_transaction_posted_with_the_picker_category_is_stored_and_audited(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    r = client.post(
        "/transactions",
        data={
            "category": str(ids["groc"]),
            "account_id": str(ids["acc"]),
            "amount": "12.34",
            "operation_date": "2026-11-20",
            "description": "milk",
        },
        headers=FROM_DIALOG,
    )
    assert r.status_code == 200
    txn_id, amount, category_id, description = _txn(db)
    assert (amount, category_id, description) == (1234, ids["groc"], "milk")
    assert _ops(db, "transaction", txn_id) == ["create"]


def test_transaction_without_a_category_reopens_the_dialog_with_the_values(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    before = db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    r = client.post(
        "/transactions",
        data={
            "account_id": str(ids["acc"]),
            "amount": "12.34",
            "operation_date": "2026-11-20",
            "description": "milk",
        },
        headers=FROM_DIALOG,
    )
    assert r.status_code == 422
    assert r.headers["HX-Retarget"] == "#modal-root"
    assert "Category : pick a category" in _html.all_text(r.text, entries.summary)
    assert _html.resolve_one(r.text, entries.hero_amount).get("value") == "12.34"
    assert _html.resolve_one(r.text, entries.field_note).get("value") == "milk"
    assert _html.resolve_one(r.text, entries.field_date).get("value") == "2026-11-20"
    assert db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == before


def test_bad_amount_marks_the_hero_and_keeps_the_picked_category(
    client: TestClient, ids: dict[str, int]
) -> None:
    r = client.post(
        "/transactions",
        data={
            "category": str(ids["groc"]),
            "account_id": str(ids["acc"]),
            "amount": "0",
            "operation_date": "2026-11-20",
        },
        headers=FROM_DIALOG,
    )
    assert r.status_code == 422
    hero = _html.resolve_one(r.text, entries.hero_amount)
    assert (hero.get("aria-invalid"), hero.get("value")) == ("true", "0")
    # Groceries has no entry yet (not a recent radio): the picker carries it as the chosen one.
    chosen = _html.resolve_one(r.text, entries.category_chosen)
    assert chosen.get("value") == str(ids["groc"])
    assert _html.text_of(r.text, entries.category_search) == "Groceries"


def test_planned_posted_with_the_picker_category_is_stored(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    r = client.post(
        "/planned",
        data={
            "category": str(ids["groc"]),
            "account_id": str(ids["acc"]),
            "amount": "99.50",
            "operation_date": "2026-12-01",
            "description": "gift",
        },
        headers=FROM_DIALOG,
    )
    assert r.status_code == 200
    row = db.execute(
        "SELECT id, amount, category_id, description FROM planned_transactions ORDER BY id DESC"
    ).fetchone()
    assert (row[1], row[2], row[3]) == (9950, ids["groc"], "gift")
    assert _ops(db, "planned_transaction", row[0]) == ["create"]


def test_planned_without_a_date_reopens_the_planned_tab(
    client: TestClient, ids: dict[str, int]
) -> None:
    r = client.post(
        "/planned",
        data={
            "category": str(ids["groc"]),
            "account_id": str(ids["acc"]),
            "amount": "5",
            "operation_date": "nope",
        },
        headers=FROM_DIALOG,
    )
    assert r.status_code == 422
    assert _html.resolve_one(r.text, entries.tab_planned).get("aria-current") == "page"
    assert "Date : invalid date" in _html.all_text(r.text, entries.summary)


def test_recurring_formula_posted_with_component_names_is_stored(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    r = client.post(
        "/recurring",
        data={
            "category": str(ids["tax"]),
            "account_id": str(ids["acc"]),
            "start_date": "2026-03-10",
            "cadence": "monthly",
            "amount_source": "formula",
            "components[0][sign]": "+",
            "components[0][percent]": "12",
            "components[0][categories]": str(ids["salary"]),
            "default_description": "tax",
        },
        headers=FROM_DIALOG,
    )
    assert r.status_code == 200
    row = db.execute(
        "SELECT id, default_amount, amount_formula FROM recurring_rules "
        "WHERE category_id = ? ORDER BY id DESC",
        (ids["tax"],),
    ).fetchone()
    assert row[1] == 1_200_00
    assert '"coefficient_bps":1200' in row[2]
    assert _ops(db, "recurring_rule", row[0]) == ["create"]


def test_recurring_fixed_failure_reopens_the_repeats_tab_with_the_values(
    client: TestClient, ids: dict[str, int]
) -> None:
    r = client.post(
        "/recurring",
        data={
            "category": str(ids["groc"]),
            "account_id": str(ids["acc"]),
            "start_date": "2026-03-10",
            "cadence": "quarterly",
            "amount_source": "fixed",
            "default_amount": "-3",
            "default_description": "box",
        },
        headers=FROM_DIALOG,
    )
    assert r.status_code == 422
    assert _html.resolve_one(r.text, entries.tab_repeats).get("aria-current") == "page"
    assert "Default Amount : amount must be positive" in _html.all_text(r.text, entries.summary)
    assert _html.resolve_one(r.text, entries.field_start).get("value") == "2026-03-10"
    assert _html.resolve_one(r.text, entries.field_note).get("value") == "box"
    quarterly = _html.resolve_one(r.text, entries.cadence_quarterly)
    assert quarterly.has_attr("checked")


def test_credit_line_fragment_answers_the_dialog_with_the_service_values(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    card = accounts_repo.create(
        db,
        USER_ID,
        NewAccount(name="Card", currency="PLN", is_liability=True, credit_limit_minor=1_000_00),
    )
    r = client.get(
        "/transactions/_limit_preview",
        params={"account_id": card.id, "category": ids["groc"], "amount": "250"},
        headers={"HX-Request": "true", "HX-Target": "credit-line"},
    )
    assert r.status_code == 200
    line = _html.text_of(r.text, entries.credit_line)
    assert line == "Card · 1,000.00 of 1,000.00 left → 750.00 after this"
    over = client.get(
        "/transactions/_limit_preview",
        params={"account_id": card.id, "category": ids["groc"], "amount": "1250"},
        headers={"HX-Request": "true", "HX-Target": "credit-line"},
    )
    assert _html.text_of(over.text, entries.credit_line) == (
        "▲ Card · 250.00 over the credit limit (1,000.00 left)"
    )
