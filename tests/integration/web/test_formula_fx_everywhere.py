"""T-Q286 (OQ-8): a cross-currency formula shows ONE number on every surface.

A PLN rule referencing an EUR category at a cached 4.30: EUR 100.00 (10_000 minor)
is 43_000 minor PLN on the ledger recurring row, the promote prefill, the live
preview and the promoted transaction; a missing rate is the documented 503.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.recurring import AmountFormula, FormulaTerm, NewRecurringRule
from budget_planner.domain.transactions import TransactionFilter
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    fx as fx_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)
from tests.ui_map import _html, edit_dialogs, ledger

USER_ID = 1
START = date(2026, 1, 1)
EUR_MINOR = 10_000
PLN_MINOR = 43_000


def _seed(settings: Settings, *, rate: str | None) -> dict[str, int]:
    conn = get_connection(settings)
    try:
        pln = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Main", currency="PLN", opening_balance=0)
        )
        eur = accounts_repo.create(
            conn, USER_ID, NewAccount(name="Euro", currency="EUR", opening_balance=0)
        )
        src = categories_repo.create(
            conn, USER_ID, NewCategory(name="Foreign", direction=Direction.INCOME)
        )
        mirror = categories_repo.create(
            conn, USER_ID, NewCategory(name="Mirror", direction=Direction.INCOME)
        )
        recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=START,
                category_id=src.id,
                account_id=eur.id,
                default_amount=EUR_MINOR,
                default_description="eur source",
            ),
        )
        rule = recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=START,
                category_id=mirror.id,
                account_id=pln.id,
                default_amount=1,
                default_description="pln formula",
                amount_formula=AmountFormula(
                    terms=(
                        FormulaTerm(
                            sign="+", coefficient_bps=10_000, source_category_ids=(src.id,)
                        ),
                    )
                ),
            ),
        )
        if rate is not None:
            fx_repo.upsert_rate(
                conn, NewFxRate(date=START, from_ccy="EUR", to_ccy="PLN", rate=Decimal(rate))
            )
    finally:
        conn.close()
    return {"rule": rule.id, "pln": pln.id, "src": src.id}


def test_recurring_row_shows_converted_amount(client: TestClient, _migrated: Settings) -> None:
    ids = _seed(_migrated, rate="4.30")
    html = client.get("/ledger?view=recurring").text
    assert "430.00" in _html.text_of(html, ledger.recurring_row(ids["rule"]))


def test_preview_converts_into_the_posted_account_currency(
    client: TestClient, _migrated: Settings
) -> None:
    ids = _seed(_migrated, rate="4.30")
    r = client.post(
        "/recurring/formula/preview",
        data={
            "account_id": str(ids["pln"]),
            "terms[0][sign]": "+",
            "terms[0][coefficient_percent]": "100",
            "terms[0][source_category_ids]": str(ids["src"]),
        },
    )
    assert r.status_code == 200
    assert _html.text_of(r.text, edit_dialogs.formula_result) == "→ next amount 430.00 PLN"


def test_promotion_stores_converted_amount_in_account_currency(
    client: TestClient, _migrated: Settings
) -> None:
    ids = _seed(_migrated, rate="4.30")
    assert client.post(f"/recurring/{ids['rule']}/promote", data={}).status_code < 400
    conn = get_connection(_migrated)
    try:
        rows = transactions_repo.list_filtered(conn, USER_ID, TransactionFilter())
    finally:
        conn.close()
    promoted = [t for t in rows if t.promoted_from_recurring_rule_id == ids["rule"]]
    assert [(t.amount, t.account_id) for t in promoted] == [(PLN_MINOR, ids["pln"])]


@pytest.mark.parametrize("surface", ["ledger", "preview", "promote"])
def test_missing_rate_is_503_everywhere(
    client: TestClient, _migrated: Settings, surface: str
) -> None:
    ids = _seed(_migrated, rate=None)
    if surface == "ledger":
        response = client.get("/ledger?view=recurring")
    elif surface == "preview":
        response = client.post(
            "/recurring/formula/preview",
            data={
                "account_id": str(ids["pln"]),
                "terms[0][sign]": "+",
                "terms[0][coefficient_percent]": "100",
                "terms[0][source_category_ids]": str(ids["src"]),
            },
        )
    else:
        response = client.post(f"/recurring/{ids['rule']}/promote", data={})
    assert response.status_code == 503
    conn = get_connection(_migrated)
    try:
        assert transactions_repo.list_filtered(conn, USER_ID, TransactionFilter()) == []
    finally:
        conn.close()
