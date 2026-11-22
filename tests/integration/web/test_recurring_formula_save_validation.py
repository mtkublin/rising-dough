"""T-Q202 (Q-028): recurring save path validates formula sources and amounts.

Foreign (other user's) or nonexistent source category ids and a formula that
resolves to zero are rejected with 422 on create and update, and nothing is
persisted (repro ``H2/h2_03_formula_foreign_sources.py``).
"""

from __future__ import annotations

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
from tests.auth_support import seed_login_user
from tests.ui_map import _html

USER_ID = 1
OTHER_USER_ID = 2
OTHER_AMOUNT = 987654
GHOST_CATEGORY_ID = 99999


@pytest.fixture
def ctx(_migrated: Settings) -> dict[str, int]:
    conn = get_connection(_migrated)
    try:
        seed_login_user(conn, user_id=OTHER_USER_ID, email="other@example.test")
        acc = accounts_repo.create(conn, USER_ID, NewAccount(name="Main", currency="PLN"))
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
        )
        target = categories_repo.create(
            conn, USER_ID, NewCategory(name="Tax", direction=Direction.EXPENSE)
        )
        empty = categories_repo.create(
            conn, USER_ID, NewCategory(name="Empty", direction=Direction.EXPENSE)
        )
        rule = recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=date(2026, 1, 1),
                category_id=cat.id,
                account_id=acc.id,
                default_amount=50000,
            ),
        )
        o_acc = accounts_repo.create(conn, OTHER_USER_ID, NewAccount(name="O", currency="PLN"))
        o_cat = categories_repo.create(
            conn, OTHER_USER_ID, NewCategory(name="OtherRent", direction=Direction.EXPENSE)
        )
        recurring_repo.create_rule(
            conn,
            OTHER_USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=date(2026, 1, 1),
                category_id=o_cat.id,
                account_id=o_acc.id,
                default_amount=OTHER_AMOUNT,
            ),
        )
        return {
            "acc": acc.id,
            "cat": cat.id,
            "target": target.id,
            "empty": empty.id,
            "rule": rule.id,
            "o_cat": o_cat.id,
        }
    finally:
        conn.close()


def _form(ctx: dict[str, int], source_ids: list[int], description: str) -> dict[str, object]:
    form: dict[str, object] = {
        "cadence": "monthly",
        "start_date": "2026-01-01",
        "category_id": str(ctx["target"]),
        "account_id": str(ctx["acc"]),
        "default_amount": "",
        "default_description": description,
        "day_of_month": "5",
        "amount_source": "formula",
        "terms[0][sign]": "+",
        "terms[0][coefficient_percent]": "100",
    }
    form["terms[0][source_category_ids]"] = [str(i) for i in source_ids]
    return form


def _snapshot(settings: Settings) -> list[tuple[object, ...]]:
    conn = get_connection(settings)
    try:
        rows = conn.execute(
            "SELECT id, user_id, default_amount, amount_formula, default_description, "
            "category_id FROM recurring_rules ORDER BY id"
        ).fetchall()
        return [tuple(r) for r in rows]
    finally:
        conn.close()


def _bad_ids(kind: str, ctx: dict[str, int]) -> list[int]:
    return {
        "foreign": [ctx["o_cat"]],
        "ghost": [GHOST_CATEGORY_ID],
        "mixed": [ctx["o_cat"], ctx["cat"]],
        "zero": [ctx["empty"]],
    }[kind]


@pytest.mark.parametrize("kind", ["foreign", "ghost", "mixed", "zero"])
def test_create_rejects_bad_formula(
    client: TestClient, ctx: dict[str, int], _migrated: Settings, kind: str
) -> None:
    before = _snapshot(_migrated)
    r = client.post("/recurring", data=_form(ctx, _bad_ids(kind, ctx), "new-formula"))
    assert r.status_code == 422
    assert "987654" not in _html.page_text(r.text)
    assert _snapshot(_migrated) == before


@pytest.mark.parametrize("kind", ["foreign", "ghost", "mixed", "zero"])
def test_update_rejects_bad_formula(
    client: TestClient, ctx: dict[str, int], _migrated: Settings, kind: str
) -> None:
    before = _snapshot(_migrated)
    r = client.post(f"/recurring/{ctx['rule']}", data=_form(ctx, _bad_ids(kind, ctx), "upd"))
    assert r.status_code == 422
    assert _snapshot(_migrated) == before
    other_rows = [row for row in before if row[1] == OTHER_USER_ID]
    assert [row[2] for row in other_rows] == [OTHER_AMOUNT]


def test_create_accepts_valid_own_source(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    r = client.post("/recurring", data=_form(ctx, [ctx["cat"]], "ok"), follow_redirects=False)
    assert r.status_code < 400
    rows = [row for row in _snapshot(_migrated) if row[4] == "ok"]
    assert len(rows) == 1
    assert rows[0][1] == USER_ID
    assert rows[0][2] == 50000
