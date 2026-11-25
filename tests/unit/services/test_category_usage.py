"""T-UR34g (ADR-0147, ADR-0148): category entry counts and picker summary."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Cadence, Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringRule
from budget_planner.domain.system_categories import RECONCILIATION_CATEGORY_NAME
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
)
from budget_planner.services import categories as categories_svc
from budget_planner.web.view_models import category_usage_text

USER_ID = 1
OTHER_USER_ID = 2


def _cat(conn: sqlite3.Connection, name: str, user_id: int = USER_ID) -> int:
    return categories_repo.create(
        conn, user_id, NewCategory(name=name, direction=Direction.EXPENSE)
    ).id


def _account(conn: sqlite3.Connection, user_id: int = USER_ID) -> int:
    return accounts_repo.create(conn, user_id, NewAccount(name="Main", currency="PLN")).id


def _txn(conn: sqlite3.Connection, cat: int, acc: int, day: date, user_id: int = USER_ID) -> int:
    return transactions_repo.create(
        conn,
        user_id,
        NewTransaction(operation_date=day, category_id=cat, account_id=acc, amount=100),
    ).id


@pytest.fixture
def acc(conn: sqlite3.Connection) -> int:
    return _account(conn)


def test_entry_count_counts_live_only(conn: sqlite3.Connection, acc: int) -> None:
    cat = _cat(conn, "Groceries")
    ids = [_txn(conn, cat, acc, date(2026, 10, d)) for d in (1, 2, 3, 4)]
    transactions_repo.soft_delete(conn, USER_ID, ids[3])

    assert categories_svc.entry_count(conn, USER_ID, cat) == 3
    assert categories_svc.entry_count(conn, USER_ID, _cat(conn, "Unused")) == 0


def test_entry_count_ignores_second_user(conn: sqlite3.Connection, acc: int) -> None:
    conn.execute("INSERT INTO users(id, name) VALUES (?, 'other')", (OTHER_USER_ID,))
    cat = _cat(conn, "Groceries")
    _txn(conn, cat, acc, date(2026, 10, 1))
    other_cat = _cat(conn, "Theirs", OTHER_USER_ID)
    other_acc = _account(conn, OTHER_USER_ID)
    _txn(conn, other_cat, other_acc, date(2026, 10, 9), OTHER_USER_ID)

    assert categories_svc.entry_count(conn, USER_ID, cat) == 1
    assert categories_svc.entry_count(conn, USER_ID, other_cat) == 0
    assert set(categories_svc.usage_by_category(conn, USER_ID)) == {cat}


def test_picker_recent_order_and_ties(conn: sqlite3.Connection, acc: int) -> None:
    a, b, c, d, e = (_cat(conn, n) for n in ("A", "B", "C", "D", "E"))
    _txn(conn, a, acc, date(2026, 10, 1))
    _txn(conn, b, acc, date(2026, 10, 20))
    _txn(conn, b, acc, date(2026, 10, 2))
    _txn(conn, c, acc, date(2026, 10, 20))  # tie with b: lower id first
    _txn(conn, d, acc, date(2026, 10, 10))
    _txn(conn, e, acc, date(2026, 9, 1))

    picker = categories_svc.picker_summary(conn, USER_ID)

    assert [x.id for x in picker.recent] == [b, c, d, a]
    assert len(picker.recent) == categories_svc.RECENT_CATEGORY_LIMIT == 4


def test_picker_excludes_archived_and_deleted_only_usage(
    conn: sqlite3.Connection, acc: int
) -> None:
    live = _cat(conn, "Live")
    archived = _cat(conn, "Archived")
    gone = _cat(conn, "Gone")
    before = categories_svc.picker_summary(conn, USER_ID).total_count
    _txn(conn, live, acc, date(2026, 10, 1))
    _txn(conn, archived, acc, date(2026, 10, 5))
    transactions_repo.soft_delete(conn, USER_ID, _txn(conn, gone, acc, date(2026, 10, 9)))
    categories_svc.archive(conn, USER_ID, archived)

    picker = categories_svc.picker_summary(conn, USER_ID)

    assert [x.id for x in picker.recent] == [live]
    assert picker.total_count == before - 1
    assert picker.total_count == len(picker.searchable)


def test_picker_never_recommends_reconciliation(conn: sqlite3.Connection, acc: int) -> None:
    recon = categories_repo.find_by_name(conn, USER_ID, RECONCILIATION_CATEGORY_NAME)
    assert recon is not None
    _txn(conn, recon.id, acc, date(2026, 10, 30))

    assert recon.id not in [x.id for x in categories_svc.picker_summary(conn, USER_ID).recent]


def test_lead_with_selected_puts_the_chosen_category_first_and_keeps_four_chips(
    conn: sqlite3.Connection, acc: int
) -> None:
    ids = [_cat(conn, n) for n in ("A", "B", "C", "D", "E")]
    for day, cid in enumerate(ids, start=1):
        _txn(conn, cid, acc, date(2026, 10, day))
    picker = categories_svc.picker_summary(conn, USER_ID)
    assert [x.id for x in picker.recent] == [ids[4], ids[3], ids[2], ids[1]]
    by_id = {c.id: c for c in picker.searchable}

    outside = categories_svc.lead_with_selected(picker, by_id[ids[0]])
    assert [x.id for x in outside.recent] == [ids[0], ids[4], ids[3], ids[2]]
    inside = categories_svc.lead_with_selected(picker, by_id[ids[2]])
    assert [x.id for x in inside.recent] == [ids[2], ids[4], ids[3], ids[1]]
    assert outside.total_count == picker.total_count
    assert outside.searchable == picker.searchable
    assert categories_svc.lead_with_selected(picker, None) is picker


def _planned(conn: sqlite3.Connection, cat: int, acc: int, user_id: int = USER_ID) -> int:
    return planned_repo.create(
        conn,
        user_id,
        NewPlannedTransaction(
            operation_date=date(2026, 11, 10), category_id=cat, account_id=acc, amount=100
        ),
    ).id


def _rule(conn: sqlite3.Connection, cat: int, acc: int, user_id: int = USER_ID) -> int:
    return recurring_repo.create_rule(
        conn,
        user_id,
        NewRecurringRule(
            cadence=Cadence.MONTHLY,
            start_date=date(2026, 11, 10),
            category_id=cat,
            account_id=acc,
            default_amount=100,
        ),
    ).id


def test_usage_counts_three_kinds_per_category(conn: sqlite3.Connection, acc: int) -> None:
    a, b = _cat(conn, "A"), _cat(conn, "B")
    for d in (1, 2, 3):
        _txn(conn, a, acc, date(2026, 10, d))
    _planned(conn, a, acc)
    _planned(conn, a, acc)
    _rule(conn, a, acc)
    _planned(conn, b, acc)
    _rule(conn, b, acc)
    _rule(conn, b, acc)

    usage = categories_svc.usage_by_category(conn, USER_ID)

    assert (usage[a].entry_count, usage[a].planned_count, usage[a].rule_count) == (3, 2, 1)
    assert usage[a].last_used == date(2026, 10, 3)
    assert (usage[b].entry_count, usage[b].planned_count, usage[b].rule_count) == (0, 1, 2)
    assert usage[b].last_used is None
    assert category_usage_text(usage[a]) == "3 entries · 2 planned · 1 rule"
    assert category_usage_text(usage[b]) == "1 planned · 2 rules"
    assert categories_svc.usage_for(conn, USER_ID, _cat(conn, "Unused")).rule_count == 0
    assert b not in [x.id for x in categories_svc.picker_summary(conn, USER_ID).recent]


def test_usage_excludes_soft_deleted_and_second_user(conn: sqlite3.Connection, acc: int) -> None:
    conn.execute("INSERT INTO users(id, name) VALUES (?, 'other')", (OTHER_USER_ID,))
    cat = _cat(conn, "A")
    _planned(conn, cat, acc)
    planned_repo.soft_delete(conn, USER_ID, _planned(conn, cat, acc))
    _rule(conn, cat, acc)
    recurring_repo.soft_delete_rule(conn, USER_ID, _rule(conn, cat, acc))
    other_acc = _account(conn, OTHER_USER_ID)
    other_cat = _cat(conn, "Theirs", OTHER_USER_ID)
    _planned(conn, other_cat, other_acc, OTHER_USER_ID)
    _rule(conn, other_cat, other_acc, OTHER_USER_ID)

    usage = categories_svc.usage_for(conn, USER_ID, cat)

    assert (usage.entry_count, usage.planned_count, usage.rule_count) == (0, 1, 1)
    assert set(categories_svc.usage_by_category(conn, USER_ID)) == {cat}
    assert categories_svc.usage_for(conn, USER_ID, other_cat).planned_count == 0


def test_picker_excludes_reconciliation_from_list_and_total_keeps_transit(
    conn: sqlite3.Connection,
) -> None:
    picker = categories_svc.picker_summary(conn, USER_ID)
    names = [c.name for c in picker.searchable]

    assert RECONCILIATION_CATEGORY_NAME not in names
    assert "Transit" in names
    assert picker.total_count == len(names)
    assert picker.total_count == len(categories_repo.list_all(conn, USER_ID)) - 1


@pytest.mark.parametrize(
    ("entries", "planned", "rules", "text"),
    [
        (0, 0, 0, None),
        (1, 0, 0, "1 entry"),
        (41, 0, 0, "41 entries"),
        (0, 2, 0, "2 planned"),
        (0, 0, 1, "1 rule"),
        (0, 0, 3, "3 rules"),
        (41, 2, 1, "41 entries · 2 planned · 1 rule"),
        (1, 0, 2, "1 entry · 2 rules"),
    ],
)
def test_category_usage_text(entries: int, planned: int, rules: int, text: str | None) -> None:
    usage = categories_svc.CategoryUsage(
        entry_count=entries, planned_count=planned, rule_count=rules, last_used=None
    )
    assert category_usage_text(usage) == text
