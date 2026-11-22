"""T-Q280 / ADR-0136: planned rows on soft-deleted accounts leave every derived number.

The ledger planned LIST still shows them (unchanged); undo of the account delete
restores every sum; the second user's rows never move the owner's figures.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass

import pytest

from budget_planner.config import Settings
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.repositories import accounts as accounts_repo, planned as planned_repo
from budget_planner.services import (
    account_planned as account_planned_svc,
    budget as budget_svc,
    forecast_events,
    ledger_totals,
    recurring as recurring_svc,
)
from budget_planner.web import ledger_data
from budget_planner.web.ledger_types import LedgerFilters
from tests.unit.services.conftest import OTHER_ID, OWNER_ID, WORLD_TODAY, World

LIVE_PLANNED = 2_000
DEAD_PLANNED = 5_000
OTHER_PLANNED = 9_999
PLANNED_DAY = dt.date(2026, 11, 20)
MONTH_START = dt.date(2026, 11, 1)
MONTH_END = dt.date(2026, 12, 1)


@dataclass(frozen=True)
class Scene:
    world: World
    dead_account_id: int


@pytest.fixture
def scene(conn: sqlite3.Connection, world_with_two_users: World) -> Scene:
    w = world_with_two_users
    conn.execute("DELETE FROM planned_transactions")
    conn.execute("DELETE FROM recurring_rule_overrides")
    conn.execute("DELETE FROM recurring_rules")
    dead = accounts_repo.create(
        conn, OWNER_ID, NewAccount(name="dead", currency="PLN", opening_balance=0)
    )
    for user_id, owner, account_id, amount in (
        (OWNER_ID, w.owner, w.owner.account_id, LIVE_PLANNED),
        (OWNER_ID, w.owner, dead.id, DEAD_PLANNED),
        (OTHER_ID, w.other, w.other.account_id, OTHER_PLANNED),
    ):
        planned_repo.create(
            conn,
            user_id,
            NewPlannedTransaction(
                operation_date=PLANNED_DAY,
                category_id=owner.category_id,
                account_id=account_id,
                amount=amount,
            ),
        )
    return Scene(w, dead.id)


def _delete(conn: sqlite3.Connection, scene: Scene) -> None:
    accounts_repo.soft_delete(conn, OWNER_ID, scene.dead_account_id)


def _undo(conn: sqlite3.Connection, scene: Scene) -> None:
    accounts_repo.undelete(conn, OWNER_ID, scene.dead_account_id)


def _committed(conn: sqlite3.Connection, scene: Scene) -> int:
    by_cat = budget_svc.committed_by_category(
        conn, OWNER_ID, start=MONTH_START, end=MONTH_END, today=WORLD_TODAY, base_currency="PLN"
    )
    return by_cat.get(scene.world.owner.category_id, 0)


def _base_of_dead(conn: sqlite3.Connection, scene: Scene) -> int:
    base_of = budget_svc.planned_base_amounts(
        conn, OWNER_ID, today=WORLD_TODAY, base_currency="PLN"
    )
    return base_of(scene.dead_account_id, DEAD_PLANNED)


def _ledger(conn: sqlite3.Connection) -> dict[str, object]:
    return ledger_data.index_context(
        conn,
        OWNER_ID,
        settings=Settings(_env_file=None),
        view="planned",
        filters=LedgerFilters(),
        today=WORLD_TODAY,
    )


def _strip(ctx: dict[str, object]) -> tuple[int, int]:
    summary = ctx["planned_summary"]
    assert isinstance(summary, ledger_totals.PlannedTotals)
    return summary.count, summary.net_minor


def _forecast_total(conn: sqlite3.Connection) -> int:
    events = forecast_events.collect_events(
        conn, OWNER_ID, today=WORLD_TODAY, end_date=dt.date(2026, 11, 30)
    )
    return sum(ev.amount_minor for evs in events.values() for ev in evs)


def test_committed_by_category_hides_deleted_account_and_undo_restores(
    conn: sqlite3.Connection, scene: Scene
) -> None:
    assert _committed(conn, scene) == LIVE_PLANNED + DEAD_PLANNED
    _delete(conn, scene)
    assert _committed(conn, scene) == LIVE_PLANNED
    _undo(conn, scene)
    assert _committed(conn, scene) == LIVE_PLANNED + DEAD_PLANNED


def test_planned_base_amounts_never_see_a_deleted_accounts_row(
    conn: sqlite3.Connection, scene: Scene
) -> None:
    assert _base_of_dead(conn, scene) == DEAD_PLANNED
    _delete(conn, scene)
    items = recurring_svc.pending_occurrences(
        conn, OWNER_ID, start=MONTH_START, end=MONTH_END, today=WORLD_TODAY, include_overdue=False
    )
    assert [(i.account_id, i.amount) for i in items] == [
        (scene.world.owner.account_id, LIVE_PLANNED)
    ]


def test_accounts_tab_planned_net_excludes_deleted_account(
    conn: sqlite3.Connection, scene: Scene
) -> None:
    window = account_planned_svc.resolve_window(conn, OWNER_ID, WORLD_TODAY)
    owner_acc = scene.world.owner.account_id
    before = account_planned_svc.planned_net_by_account(conn, OWNER_ID, window)
    assert before == {owner_acc: -LIVE_PLANNED, scene.dead_account_id: -DEAD_PLANNED}
    _delete(conn, scene)
    assert account_planned_svc.planned_net_by_account(conn, OWNER_ID, window) == {
        owner_acc: -LIVE_PLANNED
    }
    hero = account_planned_svc.compute_accounts_planned(
        conn, OWNER_ID, WORLD_TODAY, Settings(_env_file=None)
    )
    assert hero.base_net_minor == -LIVE_PLANNED
    _undo(conn, scene)
    assert account_planned_svc.planned_net_by_account(conn, OWNER_ID, window) == before


def test_ledger_strip_total_excludes_deleted_account_but_list_keeps_row(
    conn: sqlite3.Connection, scene: Scene
) -> None:
    assert _strip(_ledger(conn)) == (2, -(LIVE_PLANNED + DEAD_PLANNED))
    _delete(conn, scene)
    ctx = _ledger(conn)
    assert _strip(ctx) == (1, -LIVE_PLANNED)
    rows = ctx["rows"]
    assert isinstance(rows, list)
    assert sorted(int(r["amount_minor"]) for r in rows) == [LIVE_PLANNED, DEAD_PLANNED]
    _undo(conn, scene)
    assert _strip(_ledger(conn)) == (2, -(LIVE_PLANNED + DEAD_PLANNED))


def test_forecast_planned_events_exclude_deleted_account(
    conn: sqlite3.Connection, scene: Scene
) -> None:
    assert _forecast_total(conn) == -(LIVE_PLANNED + DEAD_PLANNED)
    _delete(conn, scene)
    assert _forecast_total(conn) == -LIVE_PLANNED
    _undo(conn, scene)
    assert _forecast_total(conn) == -(LIVE_PLANNED + DEAD_PLANNED)


def test_second_users_deleted_account_rows_are_absent_and_do_not_leak(
    conn: sqlite3.Connection, scene: Scene
) -> None:
    accounts_repo.soft_delete(conn, OTHER_ID, scene.world.other.account_id)
    _delete(conn, scene)
    assert _committed(conn, scene) == LIVE_PLANNED
    other = recurring_svc.pending_occurrences(
        conn, OTHER_ID, start=MONTH_START, end=MONTH_END, today=WORLD_TODAY, include_overdue=False
    )
    assert other == ()
    assert _strip(_ledger(conn)) == (1, -LIVE_PLANNED)
