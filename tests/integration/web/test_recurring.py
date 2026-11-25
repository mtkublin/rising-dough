"""T-035 recurring router + T-118 promote/skip routes."""

from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.domain.transactions import TransactionFilter
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)
from tests.ui_map import _html, edit_dialogs, entries, errors, ledger
from tests.ui_map.locator import by_id, role

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


def _state(db: sqlite3.Connection) -> list[tuple[object, ...]]:
    """Rules + overrides + transaction ids as plain tuples (before/after equality)."""
    rules = [
        tuple(r)
        for r in db.execute(
            "SELECT id, cadence, start_date, default_amount, active, next_due, "
            "deleted_at IS NOT NULL FROM recurring_rules ORDER BY id"
        )
    ]
    overrides = [
        tuple(r)
        for r in db.execute(
            "SELECT rule_id, occurrence_date, state, amount_override, promoted_to_txn_id "
            "FROM recurring_rule_overrides ORDER BY id"
        )
    ]
    txns = [tuple(r) for r in db.execute("SELECT id FROM transactions ORDER BY id")]
    return [*rules, *overrides, *txns]


@pytest.fixture
def ctx(_migrated: Settings) -> dict[str, int]:
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(conn, USER_ID, NewAccount(name="Main", currency="PLN"))
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Rent", direction=Direction.EXPENSE)
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
        return {"acc": acc.id, "cat": cat.id, "rule": rule.id}
    finally:
        conn.close()


def test_new_form(client: TestClient) -> None:
    r = client.get("/recurring/new", headers=_HTMX)
    assert r.status_code == 200
    assert _html.exists(r.text, entries.tab_repeats)
    start = _html.resolve_one(r.text, entries.field_start)
    assert (start.get("name"), start.get("type")) == ("start_date", "date")
    assert _html.exists(r.text, entries.cadence_group)


def test_new_form_single_term_consistent_indices(client: TestClient, ctx: dict[str, int]) -> None:
    """ADR-0047 regression: inner category loop must not shadow outer term
    loop's `loop.index0`. Single-term new form must emit every checkbox under
    `components[0][categories]`, matching the sign/percent fields (the dialog's names; the
    route reads them as terms, ``recurring_forms.parse_terms_from_form``).
    """
    # ``ctx`` seeds at least one income+expense category so
    # ``_formula_source_candidates`` yields non-empty checkbox markup.
    assert ctx["cat"] > 0
    r = client.get("/recurring/new", headers=_HTMX)
    assert r.status_code == 200
    checkbox_indices = {
        int(m.group(1)) for m in re.finditer(r'name="components\[(\d+)\]\[categories\]"', r.text)
    }
    sign_indices = {
        int(m.group(1)) for m in re.finditer(r'name="components\[(\d+)\]\[sign\]"', r.text)
    }
    # New form seeds a single empty term — both axes must agree on index 0.
    assert checkbox_indices == {0}, checkbox_indices
    assert sign_indices == {0}, sign_indices


def test_create(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        "/recurring",
        data={
            "cadence": "monthly",
            "start_date": "2026-02-01",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "default_amount": "500",
        },
    )
    assert r.status_code == 200
    assert "forecast-stale" in r.headers["HX-Trigger"]


def test_create_invalid_cadence(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    before = _state(db)
    r = client.post(
        "/recurring",
        data={
            "cadence": "bogus",
            "start_date": "2026-02-01",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "default_amount": "1",
        },
    )
    assert r.status_code == 422
    assert "cadence: invalid cadence" in _html.all_text(r.text, errors.alert)
    assert _state(db) == before


def test_create_invalid_date(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    before = _state(db)
    r = client.post(
        "/recurring",
        data={
            "cadence": "monthly",
            "start_date": "nope",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "default_amount": "1",
        },
    )
    assert r.status_code == 422
    assert "start_date: invalid date" in _html.all_text(r.text, errors.alert)
    assert _state(db) == before


def test_create_invalid_amount(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    before = _state(db)
    r = client.post(
        "/recurring",
        data={
            "cadence": "monthly",
            "start_date": "2026-02-01",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "default_amount": "-5",
        },
    )
    assert r.status_code == 422
    assert "default_amount: amount must be positive" in _html.all_text(r.text, errors.alert)
    assert _state(db) == before


def test_create_unknown_account(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    before = _state(db)
    r = client.post(
        "/recurring",
        data={
            "cadence": "monthly",
            "start_date": "2026-02-01",
            "category_id": ctx["cat"],
            "account_id": 9999,
            "default_amount": "1",
        },
    )
    assert r.status_code == 422
    assert "account_id: unknown account" in _html.all_text(r.text, errors.alert)
    assert _state(db) == before


def test_create_transit_persists_dest_account(
    client: TestClient, _migrated: Settings, ctx: dict[str, int]
) -> None:
    """Transit recurring rule must round-trip dest_account_id from the form."""
    conn = get_connection(_migrated)
    try:
        dest = accounts_repo.create(conn, USER_ID, NewAccount(name="Savings", currency="PLN"))
        transit_cat = next(
            c for c in categories_repo.list_all(conn, USER_ID) if c.direction == Direction.TRANSIT
        )
    finally:
        conn.close()
    r = client.post(
        "/recurring",
        data={
            "cadence": "monthly",
            "start_date": "2026-02-01",
            "category_id": transit_cat.id,
            "account_id": ctx["acc"],
            "dest_account_id": dest.id,
            "default_amount": "100",
        },
    )
    assert r.status_code == 200, r.text
    conn = get_connection(_migrated)
    try:
        rules = recurring_repo.list_rules(conn, USER_ID)
        created = next(r for r in rules if r.category_id == transit_cat.id)
    finally:
        conn.close()
    assert created.dest_account_id == dest.id


def test_create_transit_without_dest_rejected(
    client: TestClient, _migrated: Settings, ctx: dict[str, int]
) -> None:
    conn = get_connection(_migrated)
    try:
        transit_cat = next(
            c for c in categories_repo.list_all(conn, USER_ID) if c.direction == Direction.TRANSIT
        )
    finally:
        conn.close()
    r = client.post(
        "/recurring",
        data={
            "cadence": "monthly",
            "start_date": "2026-02-01",
            "category_id": transit_cat.id,
            "account_id": ctx["acc"],
            "dest_account_id": "",
            "default_amount": "100",
        },
    )
    assert r.status_code == 422
    assert "destination" in _html.text_of(r.text, ledger.form_errors).lower()


def test_create_transit_cross_currency_rejected(
    client: TestClient, _migrated: Settings, ctx: dict[str, int]
) -> None:
    conn = get_connection(_migrated)
    try:
        eur_acc = accounts_repo.create(conn, USER_ID, NewAccount(name="EUR", currency="EUR"))
        transit_cat = next(
            c for c in categories_repo.list_all(conn, USER_ID) if c.direction == Direction.TRANSIT
        )
    finally:
        conn.close()
    r = client.post(
        "/recurring",
        data={
            "cadence": "monthly",
            "start_date": "2026-02-01",
            "category_id": transit_cat.id,
            "account_id": ctx["acc"],
            "dest_account_id": eur_acc.id,
            "default_amount": "100",
        },
    )
    assert r.status_code == 422
    assert "currenc" in _html.text_of(r.text, ledger.form_errors).lower()


def test_update_transit_persists_dest_account(
    client: TestClient, _migrated: Settings, ctx: dict[str, int]
) -> None:
    conn = get_connection(_migrated)
    try:
        dest = accounts_repo.create(conn, USER_ID, NewAccount(name="Savings", currency="PLN"))
        transit_cat = next(
            c for c in categories_repo.list_all(conn, USER_ID) if c.direction == Direction.TRANSIT
        )
        rule = recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=date(2026, 1, 1),
                category_id=transit_cat.id,
                account_id=ctx["acc"],
                dest_account_id=dest.id,
                default_amount=10000,
            ),
        )
        new_dest = accounts_repo.create(conn, USER_ID, NewAccount(name="Brokerage", currency="PLN"))
    finally:
        conn.close()
    r = client.post(
        f"/recurring/{rule.id}",
        data={
            "cadence": "monthly",
            "start_date": "2026-03-01",
            "category_id": transit_cat.id,
            "account_id": ctx["acc"],
            "dest_account_id": new_dest.id,
            "default_amount": "250",
        },
    )
    assert r.status_code == 200, r.text
    conn = get_connection(_migrated)
    try:
        updated = recurring_repo.find_rule(conn, USER_ID, rule.id)
    finally:
        conn.close()
    assert updated is not None
    assert updated.dest_account_id == new_dest.id


def test_edit_transit_form_prefills_dest(
    client: TestClient, _migrated: Settings, ctx: dict[str, int]
) -> None:
    conn = get_connection(_migrated)
    try:
        dest = accounts_repo.create(conn, USER_ID, NewAccount(name="Savings", currency="PLN"))
        transit_cat = next(
            c for c in categories_repo.list_all(conn, USER_ID) if c.direction == Direction.TRANSIT
        )
        rule = recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=date(2026, 1, 1),
                category_id=transit_cat.id,
                account_id=ctx["acc"],
                dest_account_id=dest.id,
                default_amount=10000,
            ),
        )
    finally:
        conn.close()
    r = client.get(f"/recurring/{rule.id}/edit", headers=_HTMX)
    assert r.status_code == 200
    scope = edit_dialogs.recurring_dialog("Transit")
    picked = _html.resolve_one(r.text, edit_dialogs.field_dest(scope)).find("option", selected=True)
    assert picked is not None
    assert picked.get("value") == str(dest.id)


def test_edit(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.get(f"/recurring/{ctx['rule']}/edit", headers=_HTMX)
    assert r.status_code == 200
    assert r.headers["HX-Retarget"] == "#modal-root"
    scope = edit_dialogs.recurring_dialog("Rent")
    amount = _html.resolve_one(r.text, edit_dialogs.hero_amount(scope))
    assert (amount.get("name"), amount.get("value")) == ("default_amount", "500.00")
    start = _html.resolve_one(r.text, edit_dialogs.field_start(scope))
    assert (start.get("name"), start.get("value")) == ("start_date", "2026-01-01")
    assert _html.resolve_one(r.text, edit_dialogs.amount_fixed(scope)).has_attr("checked")
    assert not _html.resolve_one(r.text, edit_dialogs.amount_formula(scope)).has_attr("checked")
    monthly = _html.resolve_one(r.text, edit_dialogs.cadence_group(scope)).find(
        "input", attrs={"value": "monthly"}
    )
    assert monthly is not None
    assert monthly.has_attr("checked")


def test_edit_404(client: TestClient) -> None:
    r = client.get("/recurring/9999/edit")
    assert r.status_code == 404
    assert r.text == "rule: not found"


def test_update(client: TestClient, ctx: dict[str, int], db: sqlite3.Connection) -> None:
    r = client.post(
        f"/recurring/{ctx['rule']}",
        data={
            "cadence": "monthly",
            "start_date": "2026-03-01",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "default_amount": "777",
        },
    )
    assert r.status_code == 200
    stored = recurring_repo.find_rule(db, USER_ID, ctx["rule"])
    assert stored is not None
    assert stored.default_amount == 77_700
    assert stored.start_date == date(2026, 3, 1)


def test_update_404(client: TestClient, ctx: dict[str, int], db: sqlite3.Connection) -> None:
    before = _state(db)
    r = client.post(
        "/recurring/9999",
        data={
            "cadence": "monthly",
            "start_date": "2026-03-01",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "default_amount": "1",
        },
    )
    assert r.status_code == 404
    assert r.text == "not found"
    assert _state(db) == before


def test_update_invalid(client: TestClient, ctx: dict[str, int], db: sqlite3.Connection) -> None:
    before = _state(db)
    r = client.post(
        f"/recurring/{ctx['rule']}",
        data={
            "cadence": "bogus",
            "start_date": "x",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "default_amount": "-1",
        },
    )
    assert r.status_code == 422
    assert _html.all_text(r.text, edit_dialogs.summary) == (
        "3 fields need attention Repeats : invalid Start date : invalid date "
        "Default Amount : amount must be positive"
    )
    assert _state(db) == before


def test_deactivate(client: TestClient, ctx: dict[str, int], db: sqlite3.Connection) -> None:
    r = client.post(f"/recurring/{ctx['rule']}/deactivate")
    assert r.status_code == 200
    stored = recurring_repo.find_rule(db, USER_ID, ctx["rule"])
    assert stored is not None
    assert stored.active is False


def test_deactivate_404(client: TestClient, ctx: dict[str, int], db: sqlite3.Connection) -> None:
    before = _state(db)
    r = client.post("/recurring/9999/deactivate")
    assert r.status_code == 404
    assert r.text == "not found"
    assert _state(db) == before


def test_add_override_overridden_amount(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        f"/recurring/{ctx['rule']}/overrides",
        data={"year": 2026, "month": 5, "amount": "9.99"},
    )
    assert r.status_code == 200
    assert "forecast-stale" in r.headers["HX-Trigger"]


def test_add_override_accepts_comma_decimal(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    r = client.post(
        f"/recurring/{ctx['rule']}/overrides",
        data={"year": 2026, "month": 5, "amount": "9,99"},
    )
    assert r.status_code == 200
    overrides = recurring_repo.list_overrides_all(db, USER_ID, ctx["rule"])
    assert [(o.occurrence_date, o.amount_override) for o in overrides] == [(date(2026, 5, 1), 999)]


def test_override_invalid_month(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    before = _state(db)
    r = client.post(
        f"/recurring/{ctx['rule']}/overrides",
        data={"year": 2026, "month": 13, "amount": "9.99"},
    )
    assert r.status_code == 422
    assert "invalid year or month" in _html.all_text(r.text, edit_dialogs.summary)
    assert _state(db) == before


def test_override_invalid_amount(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    before = _state(db)
    r = client.post(
        f"/recurring/{ctx['rule']}/overrides",
        data={"year": 2026, "month": 5, "amount": "nope"},
    )
    assert r.status_code == 422
    assert "amount must be a decimal number within range" in _html.all_text(
        r.text, edit_dialogs.summary
    )
    assert _state(db) == before


def test_override_non_positive_amount(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    before = _state(db)
    r = client.post(
        f"/recurring/{ctx['rule']}/overrides",
        data={"year": 2026, "month": 5, "amount": "0"},
    )
    assert r.status_code == 422
    assert "amount must be positive" in _html.all_text(r.text, edit_dialogs.summary)
    assert _state(db) == before


def test_override_404_rule(client: TestClient) -> None:
    r = client.post(
        "/recurring/9999/overrides",
        data={"year": 2026, "month": 5, "amount": "9.99"},
    )
    assert r.status_code == 404
    assert r.text == "not found"


def test_delete_override(client: TestClient, ctx: dict[str, int], db: sqlite3.Connection) -> None:
    client.post(
        f"/recurring/{ctx['rule']}/overrides",
        data={"year": 2026, "month": 5, "amount": "9.99"},
    )
    assert len(recurring_repo.list_overrides_all(db, USER_ID, ctx["rule"])) == 1
    r = client.post(f"/recurring/{ctx['rule']}/overrides/2026-05-01/delete")
    assert r.status_code == 200
    assert _html.exists(r.text, ledger.recurring_row(ctx["rule"]))
    assert recurring_repo.list_overrides_all(db, USER_ID, ctx["rule"]) == []


def test_delete_override_404_rule(client: TestClient) -> None:
    r = client.post("/recurring/9999/overrides/2026-05-01/delete")
    assert r.status_code == 404
    assert r.text == "not found"


def test_delete_override_bad_date(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    before = _state(db)
    r = client.post(f"/recurring/{ctx['rule']}/overrides/bad/delete")
    assert r.status_code == 422
    assert r.text == "invalid date"
    assert _state(db) == before


# ---------------------------------------------------------------------------
# T-118 — promote + skip-next routes (ADR-0038)
# ---------------------------------------------------------------------------
def _get_rule_next_due(_migrated: Settings, rule_id: int) -> date:
    conn = get_connection(_migrated)
    try:
        rule = recurring_repo.find_rule(conn, USER_ID, rule_id)
        assert rule is not None
        return rule.next_due
    finally:
        conn.close()


def test_promote_form_renders(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.get(f"/recurring/{ctx['rule']}/promote?dialog=1", headers=_HTMX)
    assert r.status_code == 200
    assert r.headers["HX-Retarget"] == "#modal-root"
    dialog = _html.resolve_one(r.text, role("dialog", re.compile("^promote ·")))
    form = dialog.find("form")
    assert form is not None
    assert (form.get("hx-post"), form.get("hx-target")) == (
        f"/recurring/{ctx['rule']}/promote",
        "#modal-root",
    )
    assert _html.resolve_one(r.text, entries.promote_amount).get("name") == "amount"
    assert _html.resolve_one(r.text, entries.promote_date).get("name") == "operation_date"


def test_promote_form_404(client: TestClient) -> None:
    r = client.get("/recurring/9999/promote")
    assert r.status_code == 404
    assert r.text == "rule: not found"


def test_promote_submit_no_edits(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    r = client.post(f"/recurring/{ctx['rule']}/promote", data={})
    assert r.status_code == 200
    payload = json.loads(r.headers["HX-Trigger"])
    assert payload == {"ledger-stale": True, "forecast-stale": True, "budget-stale": True}

    # DB side-effect: rule's next_due advanced + one new transaction exists.
    conn = get_connection(_migrated)
    try:
        rows = transactions_repo.list_filtered(conn, USER_ID, TransactionFilter())
        assert len(rows) == 1
        assert rows[0].promoted_from_recurring_rule_id == ctx["rule"]
    finally:
        conn.close()


def test_promote_submit_404(client: TestClient, db: sqlite3.Connection) -> None:
    before = _state(db)
    r = client.post("/recurring/9999/promote", data={})
    assert r.status_code == 404
    assert r.text == "not found"
    assert _state(db) == before


def test_promote_submit_invalid_amount_422(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        f"/recurring/{ctx['rule']}/promote",
        data={"amount": "not-a-number"},
        headers=_FROM_DIALOG,
    )
    assert r.status_code == 422
    assert r.headers["HX-Retarget"] == "#modal-root"
    assert "Amount" in _html.all_text(r.text, entries.summary)
    assert _html.resolve_one(r.text, entries.promote_amount).get("value") == "not-a-number"


def test_promote_submit_zero_amount_422(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    before = _state(db)
    r = client.post(
        f"/recurring/{ctx['rule']}/promote",
        data={"amount": "0"},
        headers=_FROM_DIALOG,
    )
    assert r.status_code == 422
    assert "Amount : amount must be positive" in _html.all_text(r.text, entries.summary)
    assert _state(db) == before


def test_promote_submit_invalid_date_422(
    client: TestClient, ctx: dict[str, int], db: sqlite3.Connection
) -> None:
    before = _state(db)
    r = client.post(
        f"/recurring/{ctx['rule']}/promote",
        data={"operation_date": "not-a-date"},
        headers=_FROM_DIALOG,
    )
    assert r.status_code == 422
    assert "Date : invalid date" in _html.all_text(r.text, entries.summary)
    assert _state(db) == before


def test_promote_submit_cross_currency_transit_422(client: TestClient, _migrated: Settings) -> None:
    conn = get_connection(_migrated)
    try:
        pln = accounts_repo.create(conn, USER_ID, NewAccount(name="PLN", currency="PLN")).id
        eur = accounts_repo.create(conn, USER_ID, NewAccount(name="EUR", currency="EUR")).id
        transit = categories_repo.find_by_name(conn, USER_ID, "Transit")
        assert transit is not None
        transit_rule = recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=date(2026, 1, 5),
                category_id=transit.id,
                account_id=pln,
                dest_account_id=eur,
                default_amount=1000,
            ),
        )
        rule_id = transit_rule.id
    finally:
        conn.close()
    r = client.post(f"/recurring/{rule_id}/promote", data={}, headers=_FROM_DIALOG)
    assert r.status_code == 422
    assert "Promotion : cross-currency transit not supported" in _html.all_text(
        r.text, entries.summary
    )
    conn = get_connection(_migrated)
    try:
        assert transactions_repo.list_filtered(conn, USER_ID, TransactionFilter()) == []
    finally:
        conn.close()


def test_skip_next_advances(client: TestClient, ctx: dict[str, int], _migrated: Settings) -> None:
    before = _get_rule_next_due(_migrated, ctx["rule"])
    r = client.post(f"/recurring/{ctx['rule']}/skip-next")
    assert r.status_code == 200
    payload = json.loads(r.headers["HX-Trigger"])
    assert payload == {"ledger-stale": True, "forecast-stale": True, "budget-stale": True}
    after = _get_rule_next_due(_migrated, ctx["rule"])
    assert after > before

    # No new transaction.
    conn = get_connection(_migrated)
    try:
        rows = transactions_repo.list_filtered(conn, USER_ID, TransactionFilter())
        assert len(rows) == 0
    finally:
        conn.close()


def test_skip_next_404(client: TestClient, db: sqlite3.Connection) -> None:
    before = _state(db)
    r = client.post("/recurring/9999/skip-next")
    assert r.status_code == 404
    assert r.text == "not found"
    assert _state(db) == before


# ---------------------------------------------------------------------------
# T-122 — Ledger Recurring row actions (ADR-0038)
# ---------------------------------------------------------------------------
def test_recurring_row_renders_next_due_column(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    """T-122: the Ledger Recurring tab shows the rule's `next_due` column
    (not `start_date`) with the five row actions in place."""
    r = client.get("/ledger?view=recurring")
    assert r.status_code == 200
    # Table headers include the mockup column set (manual-audit #25 removed
    # the separate Cadence + Active columns — Cadence is now a group header
    # and Active status folds into the description column).
    for header in ("Next due", "Rule", "Category", "Amount", "Overrides"):
        assert _html.exists(r.text, ledger.column_header(header)), header
    # The skip action names the rule's next_due date (not start_date).
    expected_next = _get_rule_next_due(_migrated, ctx["rule"]).isoformat()
    actions = ledger.menu_actions(r.text, ledger.recurring_row(ctx["rule"]))
    assert actions["Skip next"].get("hx-confirm") == f"Skip {expected_next}?"
    # Five action buttons (promote / override-next / skip-next / edit / delete).
    rid = ctx["rule"]
    assert {label: (b.get("hx-get") or b.get("hx-post")) for label, b in actions.items()} == {
        "Promote": f"/recurring/{rid}/promote",
        "Override": f"/recurring/{rid}/overrides/new",
        "Skip next": f"/recurring/{rid}/skip-next",
        "Edit": f"/recurring/{rid}/edit",
        "Delete": f"/recurring/{rid}/deactivate",
    }


def test_recurring_promote_modal_shows_override_banner(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    """T-122: GET /recurring/{id}/promote renders the Override-applied
    banner iff an override exists for the current next_due."""
    next_due = _get_rule_next_due(_migrated, ctx["rule"])
    # Baseline: no override yet, no banner.
    r_before = client.get(f"/recurring/{ctx['rule']}/promote", headers=_HTMX)
    assert r_before.status_code == 200
    assert not _html.exists(r_before.text, ledger.override_applied)
    # Install an override on next_due.
    client.post(
        f"/recurring/{ctx['rule']}/overrides",
        data={"year": next_due.year, "month": next_due.month, "amount": "123.45"},
    )
    r_after = client.get(f"/recurring/{ctx['rule']}/promote", headers=_HTMX)
    assert r_after.status_code == 200
    assert _html.exists(r_after.text, ledger.override_applied)


def test_recurring_promote_submit_advances_and_fires_triggers(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    """T-122: POST /recurring/{id}/promote creates a txn, advances the row,
    and emits the three HX-Trigger events."""
    before = _get_rule_next_due(_migrated, ctx["rule"])
    r = client.post(f"/recurring/{ctx['rule']}/promote", data={})
    assert r.status_code == 200
    payload = json.loads(r.headers["HX-Trigger"])
    assert payload == {"ledger-stale": True, "forecast-stale": True, "budget-stale": True}
    after = _get_rule_next_due(_migrated, ctx["rule"])
    assert after > before
    # One transaction created.
    conn = get_connection(_migrated)
    try:
        rows = transactions_repo.list_filtered(conn, USER_ID, TransactionFilter())
        assert len(rows) == 1
    finally:
        conn.close()


def test_recurring_skip_next_advances_without_txn(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    """T-122: Skip next advances next_due but does not create a transaction."""
    before = _get_rule_next_due(_migrated, ctx["rule"])
    r = client.post(f"/recurring/{ctx['rule']}/skip-next")
    assert r.status_code == 200
    after = _get_rule_next_due(_migrated, ctx["rule"])
    assert after > before
    conn = get_connection(_migrated)
    try:
        rows = transactions_repo.list_filtered(conn, USER_ID, TransactionFilter())
        assert len(rows) == 0
    finally:
        conn.close()


def test_recurring_delete_soft_deactivates(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    """T-122: the Delete action (behavioural = deactivate soft delete) sets
    active=0; the rule row stays in the DB so historical promotions can
    still reference it."""
    r = client.post(f"/recurring/{ctx['rule']}/deactivate")
    assert r.status_code == 200
    conn = get_connection(_migrated)
    try:
        rule = recurring_repo.find_rule(conn, USER_ID, ctx["rule"], include_deleted=True)
        assert rule is not None
        assert rule.active is False
    finally:
        conn.close()


def test_recurring_delete_returns_empty_body_and_triggers_ledger_stale(
    client: TestClient, ctx: dict[str, int]
) -> None:
    """Delete returns an empty body + HX-Trigger so the row vanishes from
    the Ledger Recurring tab (hx-swap=outerHTML) and the table re-fetches."""
    r = client.post(f"/recurring/{ctx['rule']}/deactivate")
    assert r.status_code == 200
    assert r.text == ""
    triggers = json.loads(r.headers["HX-Trigger"])
    assert "ledger-stale" in triggers
    assert "forecast-stale" in triggers


def test_recurring_delete_hides_from_ledger_view(client: TestClient, ctx: dict[str, int]) -> None:
    """ADR-0038 §Ledger-UI: deactivated rules are not 'live' and must not
    appear in the Ledger Recurring tab."""
    before = client.get("/ledger?view=recurring")
    assert _html.exists(before.text, ledger.recurring_row(ctx["rule"]))

    client.post(f"/recurring/{ctx['rule']}/deactivate")

    after = client.get("/ledger?view=recurring")
    assert after.status_code == 200
    assert not _html.exists(after.text, ledger.recurring_row(ctx["rule"]))


def test_recurring_overrides_new_form_renders(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    """GET /recurring/{id}/overrides/new returns the generic override form
    with year + month pre-filled from the rule's current ``next_due``."""
    next_due = _get_rule_next_due(_migrated, ctx["rule"])
    r = client.get(f"/recurring/{ctx['rule']}/overrides/new", headers=_HTMX)
    assert r.status_code == 200
    scope = edit_dialogs.occurrence_dialog("Rent")
    form = _html.resolve_one(r.text, scope).find("form")
    assert form is not None
    assert (form.get("hx-post"), form.get("hx-target")) == (
        f"/recurring/{ctx['rule']}/overrides",
        "#modal-root",
    )
    month = _html.resolve_one(r.text, edit_dialogs.month_group(scope))
    year_input = month.find("input", attrs={"name": "year"})
    assert year_input is not None
    assert year_input.get("value") == str(next_due.year)


def test_recurring_overrides_new_form_404(client: TestClient) -> None:
    r = client.get("/recurring/9999/overrides/new")
    assert r.status_code == 404
    assert r.text == "not found"


def test_recurring_overrides_new_form_defaults_to_next_due(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    """The year input defaults to the rule's current ``next_due`` year."""
    next_due = _get_rule_next_due(_migrated, ctx["rule"])
    r = client.get(f"/recurring/{ctx['rule']}/overrides/new", headers=_HTMX)
    assert r.status_code == 200
    scope = edit_dialogs.occurrence_dialog("Rent")
    month = _html.resolve_one(r.text, edit_dialogs.month_group(scope))
    year_input = month.find("input", attrs={"name": "year"})
    month_input = month.find("input", attrs={"name": "month"})
    assert year_input is not None
    assert month_input is not None
    assert (year_input.get("value"), month_input.get("value")) == (
        str(next_due.year),
        str(next_due.month),
    )


def test_recurring_row_amount_italic_when_override_amount_set(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    """Amount cell gains ``<em data-amount-overridden>`` when the override
    on the current ``next_due`` carries an ``amount_override``."""
    next_due = _get_rule_next_due(_migrated, ctx["rule"])
    client.post(
        f"/recurring/{ctx['rule']}/overrides",
        data={"year": next_due.year, "month": next_due.month, "amount": "99.00"},
    )
    r = client.get("/ledger?view=recurring")
    assert r.status_code == 200
    row_text = _html.text_of(r.text, ledger.recurring_row(ctx["rule"]))
    assert "99.00" in row_text  # the overridden amount replaces the default


def test_promote_submit_backfilled_next_due(client: TestClient, _migrated: Settings) -> None:
    """Fresh-DB regression: a rule whose next_due was computed on insert
    (equivalent to the T-117 backfill path) promotes a transaction dated at
    that next_due."""
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.create(conn, USER_ID, NewAccount(name="Freshly", currency="PLN"))
        cat = categories_repo.create(
            conn, USER_ID, NewCategory(name="Utilities", direction=Direction.EXPENSE)
        )
        # Pick a start_date in the past so repository backfills next_due to a
        # future canonical date (not start_date itself).
        past_start = clock.today_local(Settings()) - dt.timedelta(days=800)
        rule = recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=past_start,
                category_id=cat.id,
                account_id=acc.id,
                default_amount=50_000,
            ),
        )
        backfilled = rule.next_due
    finally:
        conn.close()

    r = client.post(f"/recurring/{rule.id}/promote", data={})
    assert r.status_code == 200

    conn = get_connection(_migrated)
    try:
        rows = transactions_repo.list_filtered(
            conn, USER_ID, TransactionFilter(account_ids=(acc.id,))
        )
        assert len(rows) == 1
        assert rows[0].operation_date == backfilled
        assert rows[0].promoted_from_recurring_date == backfilled
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# ADR-0063 — recurring stop date (end_date)
# ---------------------------------------------------------------------------
def test_create_with_end_date_persists(
    client: TestClient, _migrated: Settings, ctx: dict[str, int]
) -> None:
    r = client.post(
        "/recurring",
        data={
            "cadence": "monthly",
            "start_date": "2030-02-01",
            "end_date": "2030-12-01",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "default_amount": "500",
        },
    )
    assert r.status_code == 200, r.text
    conn = get_connection(_migrated)
    try:
        rules = recurring_repo.list_rules(conn, USER_ID)
        created = next(r for r in rules if r.start_date == date(2030, 2, 1))
    finally:
        conn.close()
    assert created.end_date == date(2030, 12, 1)
    assert created.active is True


def test_create_end_date_before_start_rejected(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        "/recurring",
        data={
            "cadence": "monthly",
            "start_date": "2030-06-01",
            "end_date": "2030-01-01",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "default_amount": "500",
        },
    )
    assert r.status_code == 422
    assert "end_date" in _html.text_of(r.text, ledger.form_errors)


def test_create_end_date_in_past_marks_inactive(
    client: TestClient, _migrated: Settings, ctx: dict[str, int]
) -> None:
    """ADR-0063 §Behavioural edges — end_date < today → active=False at insert."""
    r = client.post(
        "/recurring",
        data={
            "cadence": "monthly",
            "start_date": "2020-01-01",
            "end_date": "2020-12-01",
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "default_amount": "500",
        },
    )
    assert r.status_code == 200, r.text
    conn = get_connection(_migrated)
    try:
        rules = recurring_repo.list_rules(conn, USER_ID)
        created = next(r for r in rules if r.start_date == date(2020, 1, 1))
    finally:
        conn.close()
    assert created.active is False


def test_update_end_date_before_next_due_deactivates(
    client: TestClient, _migrated: Settings, ctx: dict[str, int]
) -> None:
    """Shortening end_date below rule.next_due flips active=False in one patch."""
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.find_by_id(conn, USER_ID, ctx["acc"])
        assert acc is not None
        cat = categories_repo.find_by_id(conn, USER_ID, ctx["cat"])
        assert cat is not None
        from budget_planner.domain.recurring import PatchRecurringRule  # noqa: PLC0415

        rule = recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=date(2030, 1, 1),
                category_id=cat.id,
                account_id=acc.id,
                default_amount=50_000,
            ),
        )
        # Pin next_due to a predictable future date.
        rule = recurring_repo.update_rule(
            conn, USER_ID, rule.id, PatchRecurringRule(next_due=date(2030, 6, 1))
        )
        assert rule.active is True
    finally:
        conn.close()

    r = client.post(
        f"/recurring/{rule.id}",
        data={
            "cadence": "monthly",
            "start_date": "2030-01-01",
            "end_date": "2030-04-01",  # before next_due
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "default_amount": "500",
        },
    )
    assert r.status_code == 200, r.text
    conn = get_connection(_migrated)
    try:
        updated = recurring_repo.find_rule(conn, USER_ID, rule.id)
    finally:
        conn.close()
    assert updated is not None
    assert updated.end_date == date(2030, 4, 1)
    assert updated.active is False


def test_update_clearing_end_date_round_trips(
    client: TestClient, _migrated: Settings, ctx: dict[str, int]
) -> None:
    """Posting an empty end_date clears a previously-set stop date."""
    conn = get_connection(_migrated)
    try:
        acc = accounts_repo.find_by_id(conn, USER_ID, ctx["acc"])
        assert acc is not None
        cat = categories_repo.find_by_id(conn, USER_ID, ctx["cat"])
        assert cat is not None
        rule = recurring_repo.create_rule(
            conn,
            USER_ID,
            NewRecurringRule(
                cadence=Cadence.MONTHLY,
                start_date=date(2030, 1, 1),
                end_date=date(2030, 12, 1),
                category_id=cat.id,
                account_id=acc.id,
                default_amount=50_000,
            ),
        )
    finally:
        conn.close()
    assert rule.end_date == date(2030, 12, 1)
    r = client.post(
        f"/recurring/{rule.id}",
        data={
            "cadence": "monthly",
            "start_date": "2030-01-01",
            "end_date": "",  # explicit clear
            "category_id": ctx["cat"],
            "account_id": ctx["acc"],
            "default_amount": "500",
        },
    )
    assert r.status_code == 200, r.text
    conn = get_connection(_migrated)
    try:
        updated = recurring_repo.find_rule(conn, USER_ID, rule.id)
    finally:
        conn.close()
    assert updated is not None
    assert updated.end_date is None


def _rule_data(ctx: dict[str, int]) -> dict[str, str | int]:
    return {
        "cadence": "monthly",
        "start_date": "2026-02-01",
        "category_id": ctx["cat"],
        "account_id": ctx["acc"],
        "default_amount": "500",
    }


def test_create_off_ledger_refreshes_page_without_swap(
    client: TestClient, ctx: dict[str, int]
) -> None:
    # T-D142: the form is opened from Today etc.; no table to swap into.
    r = client.post(
        "/recurring",
        data=_rule_data(ctx),
        headers={"HX-Request": "true", "HX-Current-URL": "http://testserver/today"},
    )
    assert r.status_code == 200
    assert r.headers["HX-Reswap"] == "none"
    assert r.headers["HX-Refresh"] == "true"
    assert "ledger-stale" in r.headers["HX-Trigger"]


def test_create_on_ledger_does_not_refresh_page(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        "/recurring",
        data=_rule_data(ctx),
        headers={"HX-Request": "true", "HX-Current-URL": "http://testserver/ledger?view=recurring"},
    )
    assert r.status_code == 200
    assert r.headers["HX-Reswap"] == "none"
    assert "HX-Refresh" not in r.headers
    assert "ledger-stale" in r.headers["HX-Trigger"]


def test_new_form_posts_into_the_modal_root_not_the_ledger_table(client: TestClient) -> None:
    r = client.get("/recurring/new", headers=_HTMX)
    form = _html.resolve_one(r.text, entries.dialog).find("form")
    assert form is not None
    assert (form.get("hx-post"), form.get("hx-target")) == ("/recurring", "#modal-root")


_ON_TODAY = {"HX-Request": "true", "HX-Current-URL": "http://testserver/today"}
_ON_LEDGER = {"HX-Request": "true", "HX-Current-URL": "http://testserver/ledger?view=recurring"}


def test_edit_dialog_posts_into_the_modal_root(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.get(f"/recurring/{ctx['rule']}/edit", headers=_HTMX)
    form = _html.resolve_one(r.text, edit_dialogs.recurring_dialog("Rent")).find("form")
    assert form is not None
    assert (form.get("hx-post"), form.get("hx-target")) == (
        f"/recurring/{ctx['rule']}",
        "#modal-root",
    )


def test_update_closes_the_dialog_from_any_page(client: TestClient, ctx: dict[str, int]) -> None:
    """Today and the ledger listen for the stale events; the dialog empties out of band."""
    url = f"/recurring/{ctx['rule']}"
    for headers in (_ON_TODAY, _ON_LEDGER):
        r = client.post(url, data=_rule_data(ctx), headers=headers)
        assert r.status_code == 200
        assert "HX-Refresh" not in r.headers
        assert json.loads(r.headers["HX-Trigger"]) == {
            "forecast-stale": True,
            "ledger-stale": True,
        }
        assert _html.resolve_one(r.text, by_id("modal-root")).get_text(strip=True) == ""
        assert "Recurring rule saved" in _html.all_text(r.text, errors.status)


def test_promote_off_ledger_refreshes_and_on_ledger_does_not(
    client: TestClient, ctx: dict[str, int]
) -> None:
    off = client.post(f"/recurring/{ctx['rule']}/promote", data={}, headers=_ON_TODAY)
    assert off.status_code == 200
    assert off.headers["HX-Reswap"] == "none"
    assert off.headers["HX-Refresh"] == "true"
    on = client.post(f"/recurring/{ctx['rule']}/promote", data={}, headers=_ON_LEDGER)
    assert on.headers["HX-Reswap"] == "none"
    assert "HX-Refresh" not in on.headers


def test_override_success_closes_the_dialog_from_any_page(
    client: TestClient, ctx: dict[str, int]
) -> None:
    form = {"year": "2026", "month": "5", "amount": "12.00"}
    for headers in (_ON_TODAY, _ON_LEDGER):
        r = client.post(f"/recurring/{ctx['rule']}/overrides", data=form, headers=headers)
        assert r.status_code == 200
        assert "HX-Refresh" not in r.headers
        assert json.loads(r.headers["HX-Trigger"]) == {
            "forecast-stale": True,
            "ledger-stale": True,
        }
        assert _html.resolve_one(r.text, by_id("modal-root")).get_text(strip=True) == ""


def test_override_errors_rerender_the_dialog_with_the_message(
    client: TestClient, ctx: dict[str, int]
) -> None:
    for form, text in (
        ({"year": "2026", "month": "13", "amount": "5"}, "invalid year or month"),
        ({"year": "2026", "month": "5", "amount": "abc"}, "decimal number within range"),
        ({"year": "2026", "month": "5", "amount": "-1"}, "must be positive"),
    ):
        r = client.post(f"/recurring/{ctx['rule']}/overrides", data=form, headers=_FROM_DIALOG)
        assert r.status_code == 422
        assert r.headers["HX-Retarget"] == "#modal-root"
        assert _html.exists(r.text, edit_dialogs.occurrence_dialog("Rent"))
        assert text in _html.all_text(r.text, edit_dialogs.summary)


def test_promote_on_the_old_shell_is_still_the_slide_over(
    client: TestClient, ctx: dict[str, int]
) -> None:
    """Without ``dialog=1`` (the ledger, until T-UR09 / T-UR10) the old modal and its 422 stay."""
    r = client.get(f"/recurring/{ctx['rule']}/promote", headers=_HTMX)
    assert _html.exists(r.text, ledger.slideover)
    assert "HX-Retarget" not in r.headers
    bad = client.post(f"/recurring/{ctx['rule']}/promote", data={"amount": "0"}, headers=_HTMX)
    assert bad.status_code == 422
    assert "amount: amount must be positive" in _html.all_text(bad.text, errors.alert)
