"""New entry -> repeats -> formula posts, as the browser sends them (T-UR58).

The dialog posts ``components[i][sign|percent|categories]`` with U+2212 for a subtracted
component; a formula reads the recurring rules of its source categories in the rule's first month.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient

from budget_planner.clock import today_local
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
from tests.ui_map import _html, edit_dialogs
from tests.ui_map.locator import by_id

USER_ID = 1
FROM_DIALOG = {"HX-Request": "true", "HX-Target": "modal-root"}
_MINUS = "\N{MINUS SIGN}"


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
    cats = {
        name: categories_repo.create(db, USER_ID, NewCategory(name=name, direction=direction)).id
        for name, direction in (
            ("groc", Direction.EXPENSE),
            ("salary", Direction.INCOME),
            ("tax", Direction.EXPENSE),
        )
    }
    recurring_repo.create_rule(
        db,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 3, 1),
            category_id=cats["salary"],
            account_id=acc.id,
            default_amount=10_000_00,
        ),
    )
    return {"acc": acc.id, **cats}


def _post(
    ids: dict[str, int], *, sign: str, percent: str, source: str, start: str
) -> dict[str, str]:
    return {
        "category": str(ids["tax"]),
        "account_id": str(ids["acc"]),
        "start_date": start,
        "cadence": "monthly",
        "amount_source": "formula",
        "default_amount": "",
        "default_description": "tax",
        "components[0][sign]": sign,
        "components[0][percent]": percent,
        "components[0][categories]": source,
    }


def _rules(db: sqlite3.Connection, category_id: int) -> list[tuple[int, int, str]]:
    return [
        (r[0], r[1], r[2])
        for r in db.execute(
            "SELECT id, default_amount, amount_formula FROM recurring_rules "
            "WHERE category_id = ? ORDER BY id",
            (category_id,),
        )
    ]


def test_positive_base_plus_ten_percent_saves_the_rule_audited(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    r = client.post(
        "/recurring",
        data=_post(ids, sign="+", percent="10", source=str(ids["salary"]), start="2026-03-10"),
        headers=FROM_DIALOG,
    )
    assert r.status_code == 200
    [(rule_id, amount, formula)] = _rules(db, ids["tax"])
    assert amount == 1_000_00
    assert json.loads(formula)["terms"] == [
        {"sign": "+", "coefficient_bps": 1000, "source_category_ids": [ids["salary"]]}
    ]
    ops = db.execute(
        "SELECT operation FROM audit_log WHERE entity_type = 'recurring_rule' AND entity_id = ?",
        (rule_id,),
    ).fetchall()
    assert [o[0] for o in ops] == ["create"]


def test_another_users_rules_are_not_a_source(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    db.execute(
        "INSERT INTO users (id, name, email, password_hash) VALUES (2, 'B', 'b@example.com', 'x')"
    )
    other = accounts_repo.create(db, 2, NewAccount(name="Theirs", currency="PLN"))
    theirs = categories_repo.create(db, 2, NewCategory(name="Theirs", direction=Direction.INCOME))
    recurring_repo.create_rule(
        db,
        2,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 3, 1),
            category_id=theirs.id,
            account_id=other.id,
            default_amount=5_000_00,
        ),
    )
    r = client.post(
        "/recurring",
        data=_post(ids, sign="+", percent="10", source=str(theirs.id), start="2026-03-10"),
        headers=FROM_DIALOG,
    )
    assert r.status_code == 422
    assert _rules(db, ids["tax"]) == []
    assert db.execute("SELECT COUNT(*) FROM recurring_rules WHERE user_id = 1").fetchone()[0] == 1


def test_sources_without_recurring_amounts_say_so_once(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    r = client.post(
        "/recurring",
        data=_post(ids, sign="+", percent="10", source=str(ids["groc"]), start="2026-03-10"),
        headers=FROM_DIALOG,
    )
    assert r.status_code == 422
    lines = _html.error_lines(r.text)
    assert len(lines) == 1
    [message] = lines.values()
    assert message.startswith("▲ the picked categories have no recurring amounts in ")
    assert _rules(db, ids["tax"]) == []


def test_a_subtracted_component_is_non_positive(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int]
) -> None:
    r = client.post(
        "/recurring",
        data=_post(ids, sign=_MINUS, percent="10", source=str(ids["salary"]), start="2026-03-10"),
        headers=FROM_DIALOG,
    )
    assert r.status_code == 422
    assert list(_html.error_lines(r.text).values()) == [
        "▲ formula resolved to a non-positive amount"
    ]
    assert _rules(db, ids["tax"]) == []


def test_a_rule_starting_next_month_reads_its_sources_in_that_month(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int], _migrated: Settings
) -> None:
    today = today_local(_migrated)
    nxt = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
    later = recurring_repo.create_rule(
        db,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=nxt,
            category_id=ids["groc"],
            account_id=ids["acc"],
            default_amount=2_000_00,
        ),
    )
    assert later.id
    r = client.post(
        "/recurring",
        data=_post(ids, sign="+", percent="50", source=str(ids["groc"]), start=nxt.isoformat()),
        headers=FROM_DIALOG,
    )
    assert r.status_code == 200
    assert [a for _, a, _ in _rules(db, ids["tax"])] == [1_000_00]


def _hero_query(ids: dict[str, int], *, percent: str, source: str) -> str:
    return (
        "/add?when=repeats&dialog=1&hero=1&amount_source=formula"
        f"&account_id={ids['acc']}&category={ids['tax']}&start_date=2026-03-10"
        f"&components[0][sign]=%2B&components[0][percent]={percent}&components[0][categories]={source}"
    )


def _preview(client: TestClient, ids: dict[str, int], *, percent: str, source: int) -> str:
    return client.post(
        "/recurring/formula/preview",
        data=_post(ids, sign="+", percent=percent, source=str(source), start="2026-03-10"),
    ).text


def test_a_failure_the_formula_shows_is_not_repeated_in_the_hero(
    client: TestClient, ids: dict[str, int]
) -> None:
    hero = client.get(_hero_query(ids, percent="10", source=str(ids["groc"])), headers=FROM_DIALOG)
    assert hero.status_code == 200
    assert "no recurring amounts" not in _html.page_text(
        hero.text
    )  # the formula body says it, once
    line = _html.resolve_one(
        _preview(client, ids, percent="10", source=ids["groc"]), edit_dialogs.formula_result
    )
    assert line.get_text(strip=True).startswith("▲ the picked categories have no recurring amounts")
    assert not line.has_attr("hidden")


def test_an_incomplete_component_is_said_once_in_the_hero(
    client: TestClient, ids: dict[str, int]
) -> None:
    hero = client.get(_hero_query(ids, percent="", source=str(ids["salary"])), headers=FROM_DIALOG)
    assert _html.page_text(hero.text).count("coefficient is required for formula rules") == 1
    line = _html.resolve_one(
        _preview(client, ids, percent="", source=ids["salary"]), edit_dialogs.formula_result
    )
    assert line.has_attr("hidden")  # no visible line beside the hero note


def test_a_preview_answer_clears_the_failed_save_line_of_the_slot(
    client: TestClient, ids: dict[str, int]
) -> None:
    html = _preview(client, ids, percent="10", source=ids["salary"])
    cleared = _html.resolve_one(html, by_id("field-formula-error"))
    assert cleared.get("hx-swap-oob") == "outerHTML"  # replaced, never deleted: no missing target
    assert cleared.has_attr("hidden")
    assert cleared.get_text(strip=True) == ""
    assert _html.count(html, by_id("field-formula-error")) == 1


def test_the_error_slot_the_preview_clears_is_always_in_the_dialog(
    client: TestClient, ids: dict[str, int]
) -> None:
    """The preview's out-of-band swap targets #field-formula-error: it must exist, once, hidden."""
    page = client.get("/add?when=repeats&dialog=1", headers=FROM_DIALOG)
    assert page.status_code == 200
    assert _html.count(page.text, by_id("field-formula-error")) == 1
    assert _html.resolve_one(page.text, by_id("field-formula-error")).has_attr("hidden")


def test_a_failed_save_line_and_the_preview_share_one_slot_in_the_new_entry_dialog(
    client: TestClient, ids: dict[str, int]
) -> None:
    r = client.post(
        "/recurring",
        data=_post(ids, sign="+", percent="10", source=str(ids["groc"]), start="2026-03-10"),
        headers=FROM_DIALOG,
    )
    assert r.status_code == 422
    assert _html.count(r.text, by_id("field-formula-error")) == 1
    assert not _html.resolve_one(r.text, by_id("field-formula-error")).has_attr("hidden")


def test_the_preview_reads_the_month_of_a_later_start_date(
    client: TestClient, db: sqlite3.Connection, ids: dict[str, int], _migrated: Settings
) -> None:
    today = today_local(_migrated)
    nxt = date(today.year + (today.month == 12), today.month % 12 + 1, 1)
    recurring_repo.create_rule(
        db,
        USER_ID,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=nxt,
            category_id=ids["groc"],
            account_id=ids["acc"],
            default_amount=2_000_00,
        ),
    )
    db.commit()
    now = client.post(
        "/recurring/formula/preview",
        data=_post(ids, sign="+", percent="50", source=str(ids["groc"]), start=today.isoformat()),
    )
    later = client.post(
        "/recurring/formula/preview",
        data=_post(ids, sign="+", percent="50", source=str(ids["groc"]), start=nxt.isoformat()),
    )
    assert now.status_code == 422  # the source has no amount this month
    assert later.status_code == 200
    assert _html.text_of(later.text, edit_dialogs.formula_result) == "→ next amount 1,000.00 PLN"
