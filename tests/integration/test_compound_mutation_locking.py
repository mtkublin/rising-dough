"""T-Q204 (ADR-0137): compound mutations take the write lock up front.

Each test drives two real connections (like two request threads) at the same
planned row / recurring rule / account. Pre-fix the guard read ran outside the
transaction and the loser got ``database is locked`` (or both won).
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from datetime import date

import pytest

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.repositories import accounts, categories, planned as planned_repo
from budget_planner.repositories._shared import transaction
from budget_planner.services import (
    planned as planned_svc,
    reconciliation as reconciliation_svc,
    recurring as recurring_svc,
    users as users_svc,
)

USER_ID = 1
OTHER_USER_ID = 2

pytestmark = pytest.mark.integration


def _race(settings: Settings, fn: Callable[[sqlite3.Connection], object]) -> list[str]:
    """Run ``fn`` on two fresh connections released at the same instant."""
    barrier = threading.Barrier(2, timeout=10)
    results: list[str] = []
    lock = threading.Lock()

    def _run() -> None:
        c = get_connection(settings)
        try:
            barrier.wait()
            fn(c)
            outcome = "ok"
        except Exception as exc:
            outcome = type(exc).__name__
        finally:
            c.close()
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=_run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return sorted(results)


def _seed_other_user(conn: sqlite3.Connection) -> int:
    conn.execute("INSERT INTO users(id, name) VALUES (?, 'other')", (OTHER_USER_ID,))
    acct = accounts.create(conn, OTHER_USER_ID, NewAccount(name="Theirs", currency="PLN"))
    cat = categories.create(
        conn, OTHER_USER_ID, NewCategory(name="Theirs cat", direction=Direction.EXPENSE)
    )
    plan = planned_repo.create(
        conn,
        OTHER_USER_ID,
        NewPlannedTransaction(
            operation_date=date(2026, 1, 15), category_id=cat.id, account_id=acct.id, amount=777
        ),
    )
    return plan.id


def test_double_submit_promotes_planned_once(
    conn: sqlite3.Connection,
    settings: Settings,
    make_account: Callable[..., int],
    make_category: Callable[..., int],
    make_planned: Callable[..., int],
) -> None:
    planned_id = make_planned(account_id=make_account(), category_id=make_category(), amount=5000)
    other_planned = _seed_other_user(conn)

    outcomes = _race(
        settings,
        lambda c: planned_svc.promote_to_actual(
            c, USER_ID, planned_id, planned_svc.PromotionEdits()
        ),
    )

    assert outcomes == sorted(["ok", planned_svc.AlreadyPromotedError.__name__])
    rows = conn.execute(
        "SELECT amount FROM transactions WHERE promoted_from_planned_id = ?", (planned_id,)
    ).fetchall()
    assert [r["amount"] for r in rows] == [5000]
    theirs = conn.execute(
        "SELECT promoted_to_txn_id FROM planned_transactions WHERE id = ?", (other_planned,)
    ).fetchone()
    assert theirs["promoted_to_txn_id"] is None


def test_double_submit_never_promotes_same_recurring_occurrence_twice(
    conn: sqlite3.Connection,
    settings: Settings,
    make_account: Callable[..., int],
    make_category: Callable[..., int],
    make_rule: Callable[..., int],
) -> None:
    rule_id = make_rule(
        account_id=make_account(),
        category_id=make_category(),
        start_date=date(2026, 11, 15),
        amount=1530,
    )

    first_due = conn.execute(
        "SELECT next_due FROM recurring_rules WHERE id = ?", (rule_id,)
    ).fetchone()["next_due"]
    outcomes = _race(
        settings,
        lambda c: recurring_svc.promote_recurring(
            c, USER_ID, rule_id, recurring_svc.PromotionEdits()
        ),
    )

    # The loser re-reads the advanced next_due inside the lock and promotes the
    # NEXT occurrence, never the same one twice.
    assert outcomes == ["ok", "ok"]
    dates = [
        r["promoted_from_recurring_date"]
        for r in conn.execute(
            "SELECT promoted_from_recurring_date FROM transactions "
            "WHERE promoted_from_recurring_rule_id = ? ORDER BY 1",
            (rule_id,),
        )
    ]
    first = date.fromisoformat(first_due)
    second = date(first.year + (first.month == 12), first.month % 12 + 1, first.day)
    third = date(second.year + (second.month == 12), second.month % 12 + 1, second.day)
    assert dates == [first.isoformat(), second.isoformat()]
    nxt = conn.execute("SELECT next_due FROM recurring_rules WHERE id = ?", (rule_id,)).fetchone()
    assert nxt["next_due"] == third.isoformat()


def test_concurrent_reconcile_second_sees_first_adjustment(
    conn: sqlite3.Connection,
    settings: Settings,
    make_account: Callable[..., int],
) -> None:
    account_id = make_account(opening_balance=1000)

    outcomes = _race(
        settings,
        lambda c: reconciliation_svc.reconcile(c, USER_ID, account_id, 1500, date(2026, 11, 20)),
    )

    # One adjustment of +500; the loser sees derived == actual inside the lock.
    assert outcomes == sorted(["ok", reconciliation_svc.NoAdjustmentNeededError.__name__])
    amounts = [
        r["amount"]
        for r in conn.execute("SELECT amount FROM transactions WHERE account_id = ?", (account_id,))
    ]
    assert amounts == [500]


def test_second_writer_waits_for_the_lock_instead_of_failing(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    holder_in = threading.Event()
    release = threading.Event()
    errors: list[BaseException] = []

    def _hold() -> None:
        c = get_connection(settings)
        try:
            with transaction(c):
                holder_in.set()
                release.wait(timeout=10)
        finally:
            c.close()

    def _wait_then_write() -> None:
        c = get_connection(settings)
        try:
            with transaction(c):
                c.execute("INSERT INTO users(id, name) VALUES (50, 'late')")
        except BaseException as exc:
            errors.append(exc)
        finally:
            c.close()

    holder = threading.Thread(target=_hold)
    holder.start()
    assert holder_in.wait(timeout=10)
    waiter = threading.Thread(target=_wait_then_write)
    waiter.start()
    waiter.join(timeout=0.5)
    assert waiter.is_alive(), "second writer must queue behind the held write lock"
    release.set()
    holder.join()
    waiter.join()

    assert errors == []
    assert conn.execute("SELECT name FROM users WHERE id = 50").fetchone()["name"] == "late"


def test_mutual_admin_removal_keeps_one_admin_and_maps_loser_to_conflict(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    conn.execute("UPDATE users SET is_admin = 1, email = 'a@x.test' WHERE id = ?", (USER_ID,))
    conn.execute(
        "INSERT INTO users(id, name, email, is_admin) VALUES (?, 'b', 'b@x.test', 1)",
        (OTHER_USER_ID,),
    )
    turn = iter([(USER_ID, OTHER_USER_ID), (OTHER_USER_ID, USER_ID)])
    guard = threading.Lock()

    def _remove(c: sqlite3.Connection) -> object:
        with guard:
            actor, target = next(turn)
        return users_svc.soft_delete_user(c, actor, target)

    outcomes = _race(settings, _remove)

    assert outcomes == sorted(["ok", users_svc.UserConflict.__name__])
    live = conn.execute("SELECT id FROM users WHERE is_admin = 1 AND deleted_at IS NULL").fetchall()
    assert len(live) == 1
