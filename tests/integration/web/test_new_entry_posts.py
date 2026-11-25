"""Posts of the new-entry dialog (T-UR07b, ADR-0107, ADR-0152).

The dialog posts the picker's ``category`` (the name the vendored combobox.js owns) and the
formula's ``components[i][...]`` names; the routes read them next to the legacy ``category_id`` and
``terms[i][...]``. A failed post from the dialog (``HX-Target: modal-root``) re-renders the dialog
with the posted values.
"""

from __future__ import annotations

import json
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
from tests.ui_map.locator import role

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
    assert _html.error_lines(r.text) == {
        "catpick-new-entry-error": "▲ Pick a category",
    }
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
    assert (hero.get("aria-invalid"), hero.get("value")) == ("true", "0.00")  # as the handoff
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
    assert _html.error_lines(r.text) == {
        "field-operation_date-error": "▲ invalid date",
    }


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
    assert _html.error_lines(r.text) == {
        "field-default_amount-error": "▲ Enter an amount above 0.00",
    }
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


def test_add_serves_the_dialog_with_or_without_the_dialog_flag(
    client: TestClient, ids: dict[str, int]
) -> None:
    new = client.get("/add?when=planned&dialog=1", headers={"HX-Request": "true"})
    assert _html.resolve_one(new.text, entries.tab_planned).get("aria-current") == "page"
    assert _html.exists(new.text, entries.dialog)
    plain = client.get("/add?when=planned", headers={"HX-Request": "true"})
    assert plain.status_code == 200
    assert _html.resolve_one(plain.text, entries.tab_planned).get("aria-current") == "page"
    assert _html.exists(plain.text, entries.dialog)


def _count(db: sqlite3.Connection, table: str) -> int:
    return int(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])  # noqa: S608 - fixed names


@pytest.mark.parametrize(
    ("path", "table", "tab"),
    [
        ("/transactions", "transactions", "happened"),
        ("/planned", "planned_transactions", "planned"),
    ],
)
def test_missing_amount_is_a_human_422_not_json(
    client: TestClient,
    db: sqlite3.Connection,
    ids: dict[str, int],
    *,
    path: str,
    table: str,
    tab: str,
) -> None:
    """A post without ``amount`` (native validation bypassed) answers the dialog, not JSON."""
    before = _count(db, table)
    r = client.post(
        path,
        data={
            "category": str(ids["groc"]),
            "account_id": str(ids["acc"]),
            "operation_date": "2026-11-20",
        },
        headers=FROM_DIALOG,
    )
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("text/html")
    assert r.headers["HX-Retarget"] == "#modal-root"
    assert _html.error_lines(r.text) == {
        "field-amount-error": "▲ amount must be a decimal number within range",
    }
    assert _html.resolve_one(r.text, entries.dialog).find("form") is not None
    assert (
        _html.resolve_one(
            r.text, entries.tab_happened if tab == "happened" else entries.tab_planned
        ).get("aria-current")
        == "page"
    )
    assert _count(db, table) == before


def test_empty_post_lists_every_missing_field_in_the_dialog(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    r = client.post("/transactions", data={}, headers=FROM_DIALOG)
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "catpick-new-entry-error": "▲ Pick a category",
        "field-account_id-error": "▲ unknown account",
        "field-operation_date-error": "▲ invalid date",
    }
    assert _count(db, "transactions") == 0


def test_recurring_post_without_amount_is_a_human_422(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    before = _count(db, "recurring_rules")
    r = client.post(
        "/recurring",
        data={
            "category": str(ids["groc"]),
            "account_id": str(ids["acc"]),
            "start_date": "2026-03-10",
            "cadence": "monthly",
        },
        headers=FROM_DIALOG,
    )
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("text/html")
    assert _html.error_lines(r.text) == {
        "field-default_amount-error": "▲ amount must be a decimal number within range",
    }
    assert _count(db, "recurring_rules") == before


@pytest.mark.parametrize(
    "data", [{"operation_date": "2026-10-20", "amount": "abc"}, {"operation_date": "2026-10-20"}]
)
def test_planned_promote_with_a_bad_or_missing_amount_is_refused(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int], data: dict[str, str]
) -> None:
    """The planned amount is never promoted for text that is not an amount."""
    pl = db.execute(
        "INSERT INTO planned_transactions"
        " (user_id, operation_date, category_id, account_id, amount, description)"
        " VALUES (1, '2026-10-15', ?, ?, 12345, 'rent') RETURNING id",
        (ids["groc"], ids["acc"]),
    ).fetchone()[0]
    db.commit()
    r = client.post(f"/planned/{pl}/promote", data=data, headers=FROM_DIALOG)
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("text/html")
    assert _html.error_lines(r.text) == {
        "field-amount-error": "▲ amount must be a decimal number within range",
    }
    assert _count(db, "transactions") == 0
    promoted = db.execute(
        "SELECT promoted_to_txn_id FROM planned_transactions WHERE id = ?", (pl,)
    ).fetchone()[0]
    assert promoted is None


@pytest.mark.parametrize("amount", ["abc", "-4"])
def test_recurring_promote_with_a_bad_amount_is_refused(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int], amount: str
) -> None:
    rule = db.execute("SELECT id, next_due FROM recurring_rules ORDER BY id LIMIT 1").fetchone()
    r = client.post(f"/recurring/{rule[0]}/promote", data={"amount": amount}, headers=FROM_DIALOG)
    assert r.status_code == 422
    message = (
        "amount must be a decimal number within range"
        if amount == "abc"
        else "Enter an amount above 0.00"
    )
    assert _html.error_lines(r.text) == {"field-amount-error": f"▲ {message}"}
    assert _count(db, "transactions") == 0
    assert (
        db.execute("SELECT next_due FROM recurring_rules WHERE id = ?", (rule[0],)).fetchone()[0]
        == rule[1]
    )


_HX = {"HX-Request": "true"}


def _hero_text(html: str) -> str:
    """The hero row as text: sign, label of the amount and the currency."""
    row = _html.resolve_one(html, entries.hero_amount).parent
    assert row is not None
    return str(row.get_text(" ", strip=True))


def test_hero_follows_the_account_currency_and_the_category_sign(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    eur = accounts_repo.create(db, USER_ID, NewAccount(name="Euro", currency="EUR"))
    jpy = accounts_repo.create(db, USER_ID, NewAccount(name="Yen", currency="JPY"))
    base = "/add?when=happened&dialog=1&hero=1"
    r = client.get(f"{base}&account_id={eur.id}&category={ids['salary']}&amount=12.5", headers=_HX)
    assert r.status_code == 200
    assert "HX-Retarget" not in r.headers
    assert _hero_text(r.text) == "+ Amount EUR"
    assert _html.resolve_one(r.text, entries.hero_amount).get("value") == "12.50"  # typed, at the exponent
    r = client.get(
        f"{base}&account_id={ids['acc']}&category={ids['groc']}&amount=13000", headers=_HX
    )
    assert _html.resolve_one(r.text, entries.hero_amount).get("value") == "13,000.00"  # grouped
    r = client.get(f"{base}&account_id={ids['acc']}&amount=12x", headers=_HX)
    assert _html.resolve_one(r.text, entries.hero_amount).get("value") == "12x"  # junk as typed
    r = client.get(f"{base}&account_id={jpy.id}&category={ids['groc']}", headers=_HX)
    assert _hero_text(r.text) == "\N{MINUS SIGN} Amount JPY"
    r = client.get(f"{base}&account_id={ids['acc']}", headers=_HX)
    assert _hero_text(r.text) == "Amount PLN"


def test_repeats_hero_is_the_fixed_amount_field(client: TestClient, ids: dict[str, int]) -> None:
    r = client.get("/add?when=repeats&dialog=1", headers=_HX)
    hero = _html.resolve_one(r.text, entries.hero_amount)
    assert (hero.get("name"), hero.get("id")) == ("default_amount", "field-default_amount")


def test_hero_placeholder_follows_the_currency_exponent(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    jpy = accounts_repo.create(db, USER_ID, NewAccount(name="Yen", currency="JPY"))
    r = client.get(f"/add?when=happened&dialog=1&hero=1&account_id={jpy.id}", headers=_HX)
    assert _html.resolve_one(r.text, entries.hero_amount).get("placeholder") == "0"
    r = client.get(f"/add?when=happened&dialog=1&hero=1&account_id={ids['acc']}", headers=_HX)
    assert _html.resolve_one(r.text, entries.hero_amount).get("placeholder") == "0.00"


def test_formula_slot_refreshes_the_hero_while_typing_and_a_newer_refresh_is_queued_last(
    client: TestClient, ids: dict[str, int]
) -> None:
    r = client.get("/add?when=repeats&dialog=1", headers=_HX)
    refresh = _html.resolve_one(r.text, entries.hero_refresh)
    trigger = str(refresh.get("hx-trigger"))
    assert "keyup changed delay:400ms from:#formula-slot" in trigger
    assert "change from:#formula-slot" in trigger
    assert refresh.get("hx-sync") == "this:queue last"


def test_repeats_formula_hero_shows_the_service_next_amount(
    client: TestClient, ids: dict[str, int]
) -> None:
    query = (
        "/add?when=repeats&dialog=1&hero=1&amount_source=formula"
        f"&account_id={ids['acc']}&category={ids['tax']}"
        f"&components[0][sign]=%2B&components[0][percent]=12&components[0][categories]={ids['salary']}"
    )
    r = client.get(query, headers=_HX)
    outputs = [o for o in _html.resolve(r.text, role("status")) if o.has_attr("for")]
    assert [o.get_text(strip=True) for o in outputs] == ["1,200.00"]
    row = outputs[0].parent
    assert row is not None
    assert row.get_text(" ", strip=True) == "\N{MINUS SIGN} 1,200.00 PLN"  # signed like a typed one
    assert "\N{RIGHTWARDS ARROW} next amount 1,200.00 PLN" in _html.all_text(r.text, entries.dialog)
    # the figure is derived, never posted: the hero has no named amount input in formula mode
    assert not _html.exists(r.text, entries.hero_amount)


def test_category_id_wins_over_the_picker_category(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    """Both spellings in one post: ``category_id`` is the one stored (``category_alias``)."""
    r = client.post(
        "/transactions",
        data={
            "category_id": str(ids["groc"]),
            "category": str(ids["tax"]),
            "account_id": str(ids["acc"]),
            "amount": "3.00",
            "operation_date": "2026-11-20",
            "description": "both",
        },
        headers=FROM_DIALOG,
    )
    assert r.status_code == 200
    assert _txn(db)[2] == ids["groc"]


def _stored_terms(db: sqlite3.Connection, category_id: int) -> list[dict[str, object]]:
    raw = db.execute(
        "SELECT amount_formula FROM recurring_rules WHERE category_id = ? ORDER BY id DESC",
        (category_id,),
    ).fetchone()[0]
    terms: list[dict[str, object]] = json.loads(raw)["terms"]
    return terms


def _formula_post(ids: dict[str, int], extra: dict[str, str]) -> dict[str, str]:
    base = {
        "category": str(ids["tax"]),
        "account_id": str(ids["acc"]),
        "start_date": "2026-03-10",
        "cadence": "monthly",
        "amount_source": "formula",
    }
    return {**base, **extra}


_COMPONENTS = {
    "components[0][sign]": "+",
    "components[0][percent]": "12",
    "components[1][sign]": "\N{MINUS SIGN}",
    "components[1][percent]": "2",
}
_TERMS = {"terms[0][sign]": "+", "terms[0][coefficient_percent]": "30"}


def test_formula_from_components_stores_exactly_those_terms(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    data = {
        **_COMPONENTS,
        "components[0][categories]": str(ids["salary"]),
        "components[1][categories]": str(ids["salary"]),
    }
    r = client.post("/recurring", data=_formula_post(ids, data), headers=FROM_DIALOG)
    assert r.status_code == 200, r.text
    assert _stored_terms(db, ids["tax"]) == [
        {"coefficient_bps": 1200, "sign": "+", "source_category_ids": [ids["salary"]]},
        {"coefficient_bps": 200, "sign": "-", "source_category_ids": [ids["salary"]]},
    ]


def test_formula_from_old_shell_terms_stores_exactly_those_terms(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    data = {**_TERMS, "terms[0][source_category_ids]": str(ids["salary"])}
    r = client.post("/recurring", data=_formula_post(ids, data), headers=_HX)
    assert r.status_code == 200, r.text
    assert _stored_terms(db, ids["tax"]) == [
        {"coefficient_bps": 3000, "sign": "+", "source_category_ids": [ids["salary"]]}
    ]


def test_formula_post_with_both_spellings_uses_only_the_components(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    """Any ``components[`` key makes it a dialog post: ``terms[`` keys are ignored, not merged."""
    data = {
        **_COMPONENTS,
        "components[0][categories]": str(ids["salary"]),
        "components[1][categories]": str(ids["salary"]),
        **_TERMS,
        "terms[0][source_category_ids]": str(ids["salary"]),
        "terms[1][sign]": "+",
        "terms[1][coefficient_percent]": "5",
        "terms[1][source_category_ids]": str(ids["salary"]),
    }
    r = client.post("/recurring", data=_formula_post(ids, data), headers=FROM_DIALOG)
    assert r.status_code == 200, r.text
    assert _stored_terms(db, ids["tax"]) == [
        {"coefficient_bps": 1200, "sign": "+", "source_category_ids": [ids["salary"]]},
        {"coefficient_bps": 200, "sign": "-", "source_category_ids": [ids["salary"]]},
    ]
