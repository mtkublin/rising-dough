"""T-035 recurring router + T-118 promote/skip routes."""

from __future__ import annotations

import datetime as dt
import json
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

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

USER_ID = 1


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


def test_index_redirects_to_ledger(client: TestClient, ctx: dict[str, int]) -> None:
    """T-070: ``/recurring`` returns 302 to the unified ledger (recurring view)."""
    r = client.get("/recurring", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/ledger?view=recurring"


def test_new_form(client: TestClient) -> None:
    r = client.get("/recurring/new")
    assert r.status_code == 200
    assert 'name="cadence"' in r.text


def test_new_form_single_term_consistent_indices(client: TestClient, ctx: dict[str, int]) -> None:
    """ADR-0047 regression: inner category loop must not shadow outer term
    loop's `loop.index0`. Single-term new form must emit every checkbox under
    `terms[0][source_category_ids]`, matching the sign/coefficient fields.
    """
    # ``ctx`` seeds at least one income+expense category so
    # ``_formula_source_candidates`` yields non-empty checkbox markup.
    assert ctx["cat"] > 0
    r = client.get("/recurring/new")
    assert r.status_code == 200
    checkbox_indices = {
        int(m.group(1))
        for m in re.finditer(
            r'name="terms\[(\d+)\]\[source_category_ids\]"',
            r.text,
        )
    }
    sign_indices = {int(m.group(1)) for m in re.finditer(r'name="terms\[(\d+)\]\[sign\]"', r.text)}
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


def test_create_invalid_cadence(client: TestClient, ctx: dict[str, int]) -> None:
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


def test_create_invalid_date(client: TestClient, ctx: dict[str, int]) -> None:
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


def test_create_invalid_amount(client: TestClient, ctx: dict[str, int]) -> None:
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


def test_create_unknown_account(client: TestClient, ctx: dict[str, int]) -> None:
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
    assert "destination" in r.text.lower()


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
    assert "currenc" in r.text.lower()


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
    r = client.get(f"/recurring/{rule.id}/edit")
    assert r.status_code == 200
    # Hidden combobox value carries the dest account id.
    assert 'name="dest_account_id"' in r.text
    assert f'value="{dest.id}"' in r.text


def test_edit(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.get(f"/recurring/{ctx['rule']}/edit")
    assert r.status_code == 200
    assert 'name="default_amount"' in r.text and 'value="500.00"' in r.text


def test_edit_404(client: TestClient) -> None:
    assert client.get("/recurring/9999/edit").status_code == 404


def test_update(client: TestClient, ctx: dict[str, int]) -> None:
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


def test_update_404(client: TestClient, ctx: dict[str, int]) -> None:
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


def test_update_invalid(client: TestClient, ctx: dict[str, int]) -> None:
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


def test_deactivate(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(f"/recurring/{ctx['rule']}/deactivate")
    assert r.status_code == 200


def test_deactivate_404(client: TestClient) -> None:
    assert client.post("/recurring/9999/deactivate").status_code == 404


def test_add_override_overridden_amount(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        f"/recurring/{ctx['rule']}/overrides",
        data={"year": 2026, "month": 5, "amount": "9.99"},
    )
    assert r.status_code == 200
    assert "forecast-stale" in r.headers["HX-Trigger"]


def test_add_override_accepts_comma_decimal(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        f"/recurring/{ctx['rule']}/overrides",
        data={"year": 2026, "month": 5, "amount": "9,99"},
    )
    assert r.status_code == 200


def test_override_invalid_month(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        f"/recurring/{ctx['rule']}/overrides",
        data={"year": 2026, "month": 13, "amount": "9.99"},
    )
    assert r.status_code == 422


def test_override_invalid_amount(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        f"/recurring/{ctx['rule']}/overrides",
        data={"year": 2026, "month": 5, "amount": "nope"},
    )
    assert r.status_code == 422


def test_override_non_positive_amount(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        f"/recurring/{ctx['rule']}/overrides",
        data={"year": 2026, "month": 5, "amount": "0"},
    )
    assert r.status_code == 422


def test_override_404_rule(client: TestClient) -> None:
    r = client.post(
        "/recurring/9999/overrides",
        data={"year": 2026, "month": 5, "amount": "9.99"},
    )
    assert r.status_code == 404


def test_delete_override(client: TestClient, ctx: dict[str, int]) -> None:
    client.post(
        f"/recurring/{ctx['rule']}/overrides",
        data={"year": 2026, "month": 5, "amount": "9.99"},
    )
    r = client.post(f"/recurring/{ctx['rule']}/overrides/2026-05-01/delete")
    assert r.status_code == 200


def test_delete_override_404_rule(client: TestClient) -> None:
    assert client.post("/recurring/9999/overrides/2026-05-01/delete").status_code == 404


def test_delete_override_bad_date(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(f"/recurring/{ctx['rule']}/overrides/bad/delete")
    assert r.status_code == 422


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
    r = client.get(f"/recurring/{ctx['rule']}/promote")
    assert r.status_code == 200
    assert "Promote recurring" in r.text
    assert f"/recurring/{ctx['rule']}/promote" in r.text


def test_promote_form_404(client: TestClient) -> None:
    r = client.get("/recurring/9999/promote")
    assert r.status_code == 404


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


def test_promote_submit_404(client: TestClient) -> None:
    r = client.post("/recurring/9999/promote", data={})
    assert r.status_code == 404


def test_promote_submit_invalid_amount_422(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        f"/recurring/{ctx['rule']}/promote",
        data={"amount": "not-a-number"},
    )
    assert r.status_code == 422
    assert "amount" in r.text.lower()


def test_promote_submit_zero_amount_422(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        f"/recurring/{ctx['rule']}/promote",
        data={"amount": "0"},
    )
    assert r.status_code == 422


def test_promote_submit_invalid_date_422(client: TestClient, ctx: dict[str, int]) -> None:
    r = client.post(
        f"/recurring/{ctx['rule']}/promote",
        data={"operation_date": "not-a-date"},
    )
    assert r.status_code == 422


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
    r = client.post(f"/recurring/{rule_id}/promote", data={})
    assert r.status_code == 422


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


def test_skip_next_404(client: TestClient) -> None:
    r = client.post("/recurring/9999/skip-next")
    assert r.status_code == 404


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
    for header in ("Next due", "Account", "Category", "Amount", "Overrides"):
        assert f'<th scope="col">{header}</th>' in r.text or '<th scope="col" ' in r.text
    # Row carries data-next-due with the rule's next_due date (not start_date).
    expected_next = _get_rule_next_due(_migrated, ctx["rule"]).isoformat()
    assert expected_next in r.text
    # Five action buttons (promote / override-next / skip-next / edit / delete).
    row_fragment_markers = [
        f"/recurring/{ctx['rule']}/promote",
        f"/recurring/{ctx['rule']}/overrides/new",
        f"/recurring/{ctx['rule']}/skip-next",
        f"/recurring/{ctx['rule']}/edit",
        f"/recurring/{ctx['rule']}/deactivate",
    ]
    for marker in row_fragment_markers:
        assert marker in r.text, marker


def test_recurring_promote_modal_shows_override_banner(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    """T-122: GET /recurring/{id}/promote renders the Override-applied
    banner iff an override exists for the current next_due."""
    next_due = _get_rule_next_due(_migrated, ctx["rule"])
    # Baseline: no override yet, no banner.
    r_before = client.get(f"/recurring/{ctx['rule']}/promote")
    assert r_before.status_code == 200
    assert "Override applied" not in r_before.text
    # Install an override on next_due.
    client.post(
        f"/recurring/{ctx['rule']}/overrides",
        data={"year": next_due.year, "month": next_due.month, "amount": "123.45"},
    )
    r_after = client.get(f"/recurring/{ctx['rule']}/promote")
    assert r_after.status_code == 200
    assert "Override applied" in r_after.text


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
    assert f'id="recurring-{ctx["rule"]}"' in before.text

    client.post(f"/recurring/{ctx['rule']}/deactivate")

    after = client.get("/ledger?view=recurring")
    assert after.status_code == 200
    assert f'id="recurring-{ctx["rule"]}"' not in after.text


def test_recurring_overrides_new_form_renders(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    """GET /recurring/{id}/overrides/new returns the generic override form
    with year + month pre-filled from the rule's current ``next_due``."""
    next_due = _get_rule_next_due(_migrated, ctx["rule"])
    r = client.get(f"/recurring/{ctx['rule']}/overrides/new")
    assert r.status_code == 200
    assert f"/recurring/{ctx['rule']}/overrides" in r.text
    assert f'value="{next_due.year}"' in r.text
    assert "Override occurrence" in r.text


def test_recurring_overrides_new_form_404(client: TestClient) -> None:
    r = client.get("/recurring/9999/overrides/new")
    assert r.status_code == 404


def test_recurring_overrides_new_form_defaults_to_next_due(
    client: TestClient, ctx: dict[str, int], _migrated: Settings
) -> None:
    """The year input defaults to the rule's current ``next_due`` year."""
    next_due = _get_rule_next_due(_migrated, ctx["rule"])
    r = client.get(f"/recurring/{ctx['rule']}/overrides/new")
    assert r.status_code == 200
    assert f'value="{next_due.year}"' in r.text


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
    assert "data-amount-overridden" in r.text
    assert "data-override-present" in r.text


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
        past_start = dt.date.today() - dt.timedelta(days=800)  # noqa: DTZ011
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
    assert "end_date" in r.text


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
