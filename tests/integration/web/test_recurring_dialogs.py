"""Recurring edit dialog (fixed, formula), occurrence override and its removal (T-UR10, ADR-0107).

Values, stored rows and audit rows are asserted; a second user's rules stay untouched.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import date

import pytest
from bs4 import Tag
from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction, OverrideState
from budget_planner.domain.money import sign_glyph
from budget_planner.domain.recurring import (
    AmountFormula,
    FormulaTerm,
    NewRecurringOverride,
    NewRecurringRule,
)
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    recurring as recurring_repo,
)
from tests.ui_map import _html, edit_dialogs, entries, errors, ledger, today
from tests.ui_map.locator import by_id

USER_ID = 1
_HTMX = {"HX-Request": "true"}
_FROM_DIALOG = {"HX-Request": "true", "HX-Target": "modal-root"}


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def ids(db: sqlite3.Connection) -> dict[str, int]:
    """Rent (fixed 500.00), a Salary source (1000.00) and Taxes (formula, 20 % of Salary)."""
    acc = accounts_repo.create(db, USER_ID, NewAccount(name="Main", currency="PLN"))
    rent = categories_repo.create(
        db, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
    )
    salary = categories_repo.create(
        db, USER_ID, NewCategory(name="Salary", direction=Direction.INCOME)
    )
    taxes = categories_repo.create(
        db, USER_ID, NewCategory(name="Taxes", direction=Direction.EXPENSE)
    )

    def rule(category: int, amount: int, formula: AmountFormula | None = None) -> int:
        return recurring_repo.create_rule(
            db,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=date(2026, 1, 1),
                category_id=category,
                account_id=acc.id,
                default_amount=amount,
                default_description="note",
                amount_formula=formula,
            ),
        ).id

    twenty_percent = AmountFormula(
        terms=(FormulaTerm(sign="+", coefficient_bps=2000, source_category_ids=(salary.id,)),)
    )
    return {
        "acc": acc.id,
        "rent": rent.id,
        "salary": salary.id,
        "taxes": taxes.id,
        "rent_rule": rule(rent.id, 50_000),
        "salary_rule": rule(salary.id, 100_000),
        "taxes_rule": rule(taxes.id, 20_000, twenty_percent),
    }


def _ops(db: sqlite3.Connection, entity: str, entity_id: int) -> list[str]:
    return [
        row[0]
        for row in db.execute(
            "SELECT operation FROM audit_log WHERE entity_type = ? AND entity_id = ? ORDER BY id",
            (entity, entity_id),
        )
    ]


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


def _hero(text: str, scope_title: str, css_class: str) -> Tag:
    dialog = _html.resolve_one(text, edit_dialogs.recurring_dialog(scope_title))
    part = dialog.find(class_=css_class)
    assert isinstance(part, Tag)
    return part


def _child(parent: Tag, tag: str, name: str | None = None) -> Tag:
    found = parent.find(tag, attrs={"name": name} if name else {})
    assert isinstance(found, Tag)
    return found


def _formula_form(ids: dict[str, int], **overrides: str) -> dict[str, str]:
    return {
        "category": str(ids["taxes"]),
        "account_id": str(ids["acc"]),
        "amount_source": "formula",
        "start_date": "2026-01-01",
        "cadence": "monthly",
        "components[0][sign]": "+",
        "components[0][percent]": "25",
        "components[0][categories]": str(ids["salary"]),
        **overrides,
    }


# --- edit dialog: formula state -------------------------------------------------------------


def test_edit_a_formula_rule_shows_its_terms_and_the_computed_amount(
    client: TestClient, ids: dict[str, int]
) -> None:
    r = client.get(f"/recurring/{ids['taxes_rule']}/edit", headers=_HTMX)
    assert r.status_code == 200
    scope = edit_dialogs.recurring_dialog("Taxes")
    assert _html.resolve_one(r.text, edit_dialogs.amount_formula(scope)).has_attr("checked")
    assert _html.resolve_one(r.text, edit_dialogs.field_note(scope)).get("value") == "note"
    # the hero is the server's computed figure: 20 % of the 1000.00 Salary rule
    figure = _hero(r.text, "Taxes", "rd-dialog__amount")
    assert (figure.name, figure.get_text()) == ("output", "200.00")
    # the note sits in the formula body (handoff), not in the hero band
    assert _hero(r.text, "Taxes", "rd-dialog__hero").find(class_="rd-dialog__hero-note") is None
    group = _html.resolve_one(r.text, edit_dialogs.formula_group(scope))
    assert _child(group, "output").get_text() == "→ next amount 200.00 PLN"
    assert _hero(r.text, "Taxes", "rd-dialog__sign").get_text() == sign_glyph(True)
    percent = _html.resolve_one(r.text, edit_dialogs.formula_percent(scope))
    assert percent.get("value") == "20"
    # the form carries the rule id so the preview leaves the rule out of its own sources
    hidden = _html.resolve_one(r.text, edit_dialogs.recurring_dialog("Taxes")).find(
        "input", attrs={"name": "draft_rule_id"}
    )
    assert hidden is not None
    assert hidden.get("value") == str(ids["taxes_rule"])


def test_hero_refresh_of_a_formula_rule_follows_the_form(
    client: TestClient, ids: dict[str, int]
) -> None:
    query = (
        f"hero=1&amount_source=formula&category={ids['taxes']}&account_id={ids['acc']}"
        f"&components[0][sign]=%2B&components[0][percent]=50"
        f"&components[0][categories]={ids['salary']}"
    )
    r = client.get(f"/recurring/{ids['taxes_rule']}/edit?{query}", headers=_HTMX)
    assert r.status_code == 200
    assert "HX-Retarget" not in r.headers
    assert _hero(r.text, "Taxes", "rd-dialog__amount").get_text() == "500.00"


def test_preview_leaves_the_edited_rule_out_of_its_sources(
    client: TestClient, ids: dict[str, int]
) -> None:
    r = client.post(
        "/recurring/formula/preview",
        data={
            "draft_rule_id": str(ids["taxes_rule"]),
            "account_id": str(ids["acc"]),
            "terms[0][sign]": "+",
            "terms[0][coefficient_percent]": "10",
            "terms[0][source_category_ids]": str(ids["salary"]),
        },
    )
    assert r.status_code == 200
    assert _html.text_of(r.text, edit_dialogs.formula_result) == "→ next amount 100.00 PLN"


# --- update: stored terms and amounts -------------------------------------------------------


def test_update_to_a_new_formula_stores_the_terms_and_the_snapshot(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection
) -> None:
    r = client.post(
        f"/recurring/{ids['taxes_rule']}",
        data=_formula_form(ids, **{"components[0][sign]": "+", "components[0][percent]": "25"}),
        headers=_FROM_DIALOG,
    )
    assert r.status_code == 200
    stored = recurring_repo.find_rule(db, USER_ID, ids["taxes_rule"])
    assert stored is not None
    assert stored.amount_formula == AmountFormula(
        terms=(FormulaTerm(sign="+", coefficient_bps=2500, source_category_ids=(ids["salary"],)),)
    )
    assert stored.default_amount == 25_000  # 25 % of 1000.00
    assert _ops(db, "recurring_rule", ids["taxes_rule"]) == ["create", "update"]


def test_update_a_fixed_rule_to_a_formula_and_back(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection
) -> None:
    to_formula = client.post(
        f"/recurring/{ids['rent_rule']}",
        data=_formula_form(ids, category=str(ids["rent"])),
        headers=_FROM_DIALOG,
    )
    assert to_formula.status_code == 200
    stored = recurring_repo.find_rule(db, USER_ID, ids["rent_rule"])
    assert stored is not None
    assert stored.amount_formula is not None
    back = client.post(
        f"/recurring/{ids['rent_rule']}",
        data={
            "category": str(ids["rent"]),
            "account_id": str(ids["acc"]),
            "amount_source": "fixed",
            "default_amount": "321.50",
            "start_date": "2026-01-01",
            "cadence": "monthly",
        },
        headers=_FROM_DIALOG,
    )
    assert back.status_code == 200
    stored = recurring_repo.find_rule(db, USER_ID, ids["rent_rule"])
    assert stored is not None
    assert (stored.amount_formula, stored.default_amount) == (None, 32_150)
    assert _ops(db, "recurring_rule", ids["rent_rule"]) == ["create", "update", "update"]


def test_empty_formula_is_a_human_422_and_writes_nothing(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection
) -> None:
    audit = _ops(db, "recurring_rule", ids["taxes_rule"])
    form = _formula_form(ids)
    del form["components[0][categories]"]
    del form["components[0][percent]"]
    r = client.post(f"/recurring/{ids['taxes_rule']}", data=form, headers=_FROM_DIALOG)
    assert r.status_code == 422
    assert r.headers["HX-Retarget"] == "#modal-root"
    assert _html.error_lines(r.text) == {
        "field-formula": "▲ coefficient is required for formula rules",
    }
    # the dialog comes back in the formula state with the posted note
    scope = edit_dialogs.recurring_dialog("Taxes")
    assert _html.resolve_one(r.text, edit_dialogs.amount_formula(scope)).has_attr("checked")
    stored = recurring_repo.find_rule(db, USER_ID, ids["taxes_rule"])
    assert stored is not None
    assert stored.default_amount == 20_000
    assert _ops(db, "recurring_rule", ids["taxes_rule"]) == audit


def test_incomplete_component_without_categories_is_rejected(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection
) -> None:
    form = _formula_form(ids)
    del form["components[0][categories]"]
    r = client.post(f"/recurring/{ids['taxes_rule']}", data=form, headers=_FROM_DIALOG)
    assert r.status_code == 422
    stored = recurring_repo.find_rule(db, USER_ID, ids["taxes_rule"])
    assert stored is not None
    assert stored.default_amount == 20_000


def test_update_with_nothing_posted_names_the_missing_fields(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection
) -> None:
    r = client.post(f"/recurring/{ids['rent_rule']}", data={}, headers=_FROM_DIALOG)
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "catpick-edit-recurring-error": "▲ pick a category",
        "field-account_id-error": "▲ unknown account",
        "field-start_date-error": "▲ invalid date",
        "field-cadence-error": "▲ invalid",
    }
    stored = recurring_repo.find_rule(db, USER_ID, ids["rent_rule"])
    assert stored is not None
    assert stored.default_amount == 50_000


# --- occurrence override --------------------------------------------------------------------


def test_override_dialog_opens_on_the_occurrence_date(
    client: TestClient, ids: dict[str, int]
) -> None:
    r = client.get(
        f"/recurring/{ids['rent_rule']}/overrides/new?occurrence_date=2026-05-01", headers=_HTMX
    )
    assert r.status_code == 200
    scope = edit_dialogs.occurrence_dialog("Rent")
    month = _html.resolve_one(r.text, edit_dialogs.month_group(scope))
    assert (_child(month, "output").get_text(), _child(month, "input", "year").get("value")) == (
        "May 2026",
        "2026",
    )
    assert _child(month, "input", "month").get("value") == "5"
    amount = _html.resolve_one(r.text, edit_dialogs.hero_amount(scope))
    assert (amount.get("name"), amount.get("value")) == ("amount", "500.00")
    prev = _html.resolve_one(r.text, edit_dialogs.month_prev(scope))
    nxt = _html.resolve_one(r.text, edit_dialogs.month_next(scope))
    assert (
        prev.get("hx-get")
        == f"/recurring/{ids['rent_rule']}/overrides/new?occurrence_date=2026-04-01"
    )
    assert (
        nxt.get("hx-get")
        == f"/recurring/{ids['rent_rule']}/overrides/new?occurrence_date=2026-06-01"
    )


def test_override_dialog_prefills_the_stored_override_of_that_month(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection
) -> None:
    recurring_repo.upsert_override(
        db,
        USER_ID,
        NewRecurringOverride(
            rule_id=ids["rent_rule"],
            occurrence_date=date(2026, 5, 1),
            state=OverrideState.OVERRIDDEN,
            amount_override=12_345,
            description_override=None,
            date_override=None,
        ),
    )
    r = client.get(
        f"/recurring/{ids['rent_rule']}/overrides/new?occurrence_date=2026-05-20", headers=_HTMX
    )
    scope = edit_dialogs.occurrence_dialog("Rent")
    assert _html.resolve_one(r.text, edit_dialogs.hero_amount(scope)).get("value") == "123.45"


def test_override_dialog_rejects_a_bad_occurrence_date(
    client: TestClient, ids: dict[str, int]
) -> None:
    r = client.get(
        f"/recurring/{ids['rent_rule']}/overrides/new?occurrence_date=nope", headers=_HTMX
    )
    assert r.status_code == 422


def test_override_save_stores_the_row_and_the_audit(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection
) -> None:
    r = client.post(
        f"/recurring/{ids['rent_rule']}/overrides",
        data={"year": "2026", "month": "5", "amount": "77,70"},
        headers=_FROM_DIALOG,
    )
    assert r.status_code == 200
    assert json.loads(r.headers["HX-Trigger"]) == {"forecast-stale": True, "ledger-stale": True}
    assert _html.resolve_one(r.text, by_id("modal-root")).get_text(strip=True) == ""
    assert "Override saved" in _html.all_text(r.text, errors.status)
    rows = db.execute(
        "SELECT id, rule_id, occurrence_date, state, amount_override FROM recurring_rule_overrides"
    ).fetchall()
    assert [tuple(row)[1:] for row in rows] == [
        (ids["rent_rule"], "2026-05-01", "overridden", 7_770)
    ]
    assert _ops(db, "recurring_override", rows[0][0]) == ["create"]


def test_override_in_a_month_without_an_occurrence_is_a_422(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection
) -> None:
    before = db.execute("SELECT COUNT(*) FROM recurring_rule_overrides").fetchone()[0]
    db.execute(
        "UPDATE recurring_rules SET end_date = '2026-03-01' WHERE id = ?", (ids["rent_rule"],)
    )
    db.commit()
    r = client.post(
        f"/recurring/{ids['rent_rule']}/overrides",
        data={"year": "2026", "month": "8", "amount": "5"},
        headers=_FROM_DIALOG,
    )
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-month-error": "▲ rule has no occurrence in 2026-08",
    }
    assert db.execute("SELECT COUNT(*) FROM recurring_rule_overrides").fetchone()[0] == before


# --- override removal -----------------------------------------------------------------------


def test_remove_override_confirm_and_delete(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection
) -> None:
    client.post(
        f"/recurring/{ids['rent_rule']}/overrides",
        data={"year": "2026", "month": "5", "amount": "9.99"},
        headers=_FROM_DIALOG,
    )
    override_id = db.execute("SELECT id FROM recurring_rule_overrides").fetchone()[0]
    confirm = client.get(
        f"/recurring/{ids['rent_rule']}/overrides/new?occurrence_date=2026-05-01&remove=1",
        headers=_HTMX,
    )
    assert confirm.status_code == 200
    scope = edit_dialogs.remove_dialog()
    assert "Rent · May 2026 goes back to the rule amount 500.00 PLN." in _html.all_text(
        confirm.text, scope
    )
    form = _html.resolve_one(confirm.text, scope).find("form")
    assert form is not None
    assert form.get("hx-post") == f"/recurring/{ids['rent_rule']}/overrides/2026-05-01/delete"
    gone = client.post(
        f"/recurring/{ids['rent_rule']}/overrides/2026-05-01/delete", headers=_FROM_DIALOG
    )
    assert gone.status_code == 200
    assert json.loads(gone.headers["HX-Trigger"]) == {"forecast-stale": True, "ledger-stale": True}
    assert _html.resolve_one(gone.text, by_id("modal-root")).get_text(strip=True) == ""
    assert db.execute("SELECT COUNT(*) FROM recurring_rule_overrides").fetchone()[0] == 0
    assert _ops(db, "recurring_override", override_id) == ["create", "delete"]


def test_remove_confirm_without_an_override_is_404(client: TestClient, ids: dict[str, int]) -> None:
    r = client.get(
        f"/recurring/{ids['rent_rule']}/overrides/new?occurrence_date=2026-05-01&remove=1",
        headers=_HTMX,
    )
    assert r.status_code == 404


# --- a second user -------------------------------------------------------------------------


def test_another_users_rule_is_not_reachable(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection
) -> None:
    theirs = _other_users_rule(db)
    before = db.execute(
        "SELECT default_amount, cadence FROM recurring_rules WHERE id = ?", (theirs,)
    ).fetchone()
    assert client.get(f"/recurring/{theirs}/edit", headers=_HTMX).status_code == 404
    assert client.get(f"/recurring/{theirs}/overrides/new", headers=_HTMX).status_code == 404
    update = client.post(
        f"/recurring/{theirs}", data=_formula_form(ids, amount_source="fixed"), headers=_FROM_DIALOG
    )
    assert update.status_code == 404
    override = client.post(
        f"/recurring/{theirs}/overrides",
        data={"year": "2026", "month": "5", "amount": "5"},
        headers=_FROM_DIALOG,
    )
    assert override.status_code == 404
    assert client.post(f"/recurring/{theirs}/overrides/2026-05-01/delete").status_code == 404
    after = db.execute(
        "SELECT default_amount, cadence FROM recurring_rules WHERE id = ?", (theirs,)
    ).fetchone()
    assert tuple(after) == tuple(before)
    assert db.execute("SELECT COUNT(*) FROM recurring_rule_overrides").fetchone()[0] == 0


# --- formula cycles ------------------------------------------------------------------------


def test_create_with_a_formula_over_its_own_category_is_a_422_and_writes_nothing(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection
) -> None:
    rules = db.execute("SELECT COUNT(*) FROM recurring_rules").fetchone()[0]
    audit = db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    form = _formula_form(ids, **{"components[0][categories]": str(ids["taxes"])})
    r = client.post("/recurring", data=form, headers=_FROM_DIALOG)
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-formula-error": "▲ a formula cannot reference its own category",
    }
    assert db.execute("SELECT COUNT(*) FROM recurring_rules").fetchone()[0] == rules
    assert db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == audit


def test_create_with_an_indirect_cycle_is_a_422(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection
) -> None:
    # Taxes reads Salary; a new rule posting to Salary may not read Taxes
    rules = db.execute("SELECT COUNT(*) FROM recurring_rules").fetchone()[0]
    form = _formula_form(
        ids, category=str(ids["salary"]), **{"components[0][categories]": str(ids["taxes"])}
    )
    r = client.post("/recurring", data=form, headers=_FROM_DIALOG)
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-formula-error": "▲ formula would create a cycle via rule 3",
    }
    assert db.execute("SELECT COUNT(*) FROM recurring_rules").fetchone()[0] == rules


def test_edit_to_an_indirect_cycle_is_a_422(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection
) -> None:
    form = _formula_form(
        ids,
        category=str(ids["salary"]),
        **{"components[0][categories]": str(ids["taxes"])},
    )
    r = client.post(f"/recurring/{ids['salary_rule']}", data=form, headers=_FROM_DIALOG)
    assert r.status_code == 422
    stored = recurring_repo.find_rule(db, USER_ID, ids["salary_rule"])
    assert stored is not None
    assert (stored.amount_formula, stored.default_amount) == (None, 100_000)


def test_preview_names_the_cycle_of_a_new_rule(client: TestClient, ids: dict[str, int]) -> None:
    r = client.post(
        "/recurring/formula/preview",
        data={
            "category": str(ids["taxes"]),
            "account_id": str(ids["acc"]),
            "terms[0][sign]": "+",
            "terms[0][coefficient_percent]": "10",
            "terms[0][source_category_ids]": str(ids["taxes"]),
        },
    )
    assert r.status_code == 422
    assert "a formula cannot reference its own category" in _html.text_of(
        r.text, edit_dialogs.formula_result
    )


def _reads(category_id: int) -> AmountFormula:
    return AmountFormula(
        terms=(FormulaTerm(sign="+", coefficient_bps=1000, source_category_ids=(category_id,)),)
    )


def _stored_cycle(db: sqlite3.Connection, ids: dict[str, int], settings: Settings) -> int:
    """Two rules that read each other's category (saved before the create-time check)."""
    db.execute("DELETE FROM recurring_rules")
    made = {}
    for name, other in (("taxes", "rent"), ("rent", "taxes")):
        made[name] = recurring_repo.create_rule(
            db,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=clock.today_local(settings),
                category_id=ids[name],
                account_id=ids["acc"],
                default_amount=10_000,
                default_description=f"{name}-cycle",
                amount_formula=_reads(ids[other]),
            ),
        ).id
    db.commit()
    return made["taxes"]


def test_today_survives_a_stored_cycle_and_marks_it(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection, _migrated: Settings
) -> None:
    taxes_rule = _stored_cycle(db, ids, _migrated)
    r = client.get("/today")
    assert r.status_code == 200
    row = _html.all_text(r.text, today.upcoming_recurring(taxes_rule))
    assert "taxes-cycle \N{MIDDLE DOT} formula cycle" in row
    assert "0.00" in row


def test_promoting_a_stored_cycle_is_a_human_422(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection, _migrated: Settings
) -> None:
    taxes_rule = _stored_cycle(db, ids, _migrated)
    txns = db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    r = client.post(f"/recurring/{taxes_rule}/promote", data={}, headers=_FROM_DIALOG)
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-promotion": (
            "▲ formula cycle detected via rule 1 (ancestors: [1, 2])"
            " — edit the formula or override this occurrence"
        ),
    }
    assert db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == txns


def test_ledger_row_of_a_stored_cycle_shows_zero_and_the_warning(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection, _migrated: Settings
) -> None:
    taxes_rule = _stored_cycle(db, ids, _migrated)
    r = client.get("/ledger?view=recurring&date_from=2000-01-01&date_to=2099-12-31")
    assert r.status_code == 200
    row = _html.all_text(r.text, ledger.recurring_row(taxes_rule))
    assert "taxes-cycle \N{MIDDLE DOT} formula cycle" in row
    assert "0.00 PLN" in row
    assert "100.00" not in row


def test_promote_dialog_of_a_stored_cycle_prefills_zero_and_warns(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection, _migrated: Settings
) -> None:
    taxes_rule = _stored_cycle(db, ids, _migrated)
    r = client.get(f"/recurring/{taxes_rule}/promote?dialog=1", headers=_HTMX)
    assert r.status_code == 200
    assert _html.resolve_one(r.text, entries.promote_amount).get("value") == "0.00"
    assert "formula cycle" in _html.page_text(r.text)


def test_editing_a_stored_cycle_that_keeps_it_is_a_422_and_writes_nothing(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection, _migrated: Settings
) -> None:
    taxes_rule = _stored_cycle(db, ids, _migrated)
    ops = _ops(db, "recurring_rule", taxes_rule)
    audit = db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    form = _formula_form(ids, **{"components[0][categories]": str(ids["rent"])})
    r = client.post(f"/recurring/{taxes_rule}", data=form, headers=_FROM_DIALOG)
    assert r.status_code == 422
    assert _html.error_lines(r.text) == {
        "field-formula": "▲ formula would create a cycle via rule 2",
    }
    stored = recurring_repo.find_rule(db, USER_ID, taxes_rule)
    assert stored is not None
    assert stored.amount_formula == _reads(ids["rent"])
    assert stored.default_amount == 10_000
    assert _ops(db, "recurring_rule", taxes_rule) == ops
    assert db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == audit


def test_editing_a_stored_cycle_to_remove_it_succeeds(
    client: TestClient, ids: dict[str, int], db: sqlite3.Connection, _migrated: Settings
) -> None:
    taxes_rule = _stored_cycle(db, ids, _migrated)
    form = _formula_form(ids, amount_source="fixed", default_amount="321.50")
    r = client.post(f"/recurring/{taxes_rule}", data=form, headers=_FROM_DIALOG)
    assert r.status_code == 200
    stored = recurring_repo.find_rule(db, USER_ID, taxes_rule)
    assert stored is not None
    assert (stored.amount_formula, stored.default_amount) == (None, 32_150)
    assert "update" in _ops(db, "recurring_rule", taxes_rule)
