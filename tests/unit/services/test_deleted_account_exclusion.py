"""T-Q276 / ADR-0136: soft-deleted accounts are hidden from every derived number.

Archived categories still count. Every figure is pinned exactly and the second user's
live and deleted accounts never move the owner's numbers.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass

import pytest

from budget_planner.config import Settings
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.categories import NewCategory
from budget_planner.domain.enums import Direction
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    transactions as transactions_repo,
)
from budget_planner.services import (
    analytics as analytics_svc,
    balance as balance_svc,
    budget as budget_svc,
    forecast as forecast_svc,
    fortune as fortune_svc,
    fx as fx_svc,
)
from tests.unit.services.conftest import (
    OTHER_ID,
    OWNER_BALANCE,
    OWNER_ID,
    WORLD_DAY,
    WORLD_TODAY,
    World,
    txn_amount,
)

DEAD_OPENING = 50_000
DEAD_EXPENSE = 3_000
DEAD_INCOME = 20_000
OTHER_DEAD_EXPENSE = 9_000
ARCHIVED_CAT_EXPENSE = 2_500
LIVE_EXPENSE = txn_amount(OWNER_ID)  # 1_000, on the owner's live account
LIVE_BALANCE = OWNER_BALANCE - LIVE_EXPENSE - ARCHIVED_CAT_EXPENSE  # 119_956
DEAD_BALANCE = DEAD_OPENING - DEAD_EXPENSE + DEAD_INCOME  # 67_000
MONTH = (dt.date(2026, 11, 1), dt.date(2026, 11, 30))


@dataclass(frozen=True)
class Scene:
    world: World
    dead_account_id: int
    archived_category_id: int


def _txn(
    conn: sqlite3.Connection,
    user_id: int,
    category_id: int,
    account_id: int,
    amount: int,
) -> None:
    transactions_repo.create(
        conn,
        user_id,
        NewTransaction(
            operation_date=WORLD_DAY,
            category_id=category_id,
            account_id=account_id,
            amount=amount,
        ),
    )


@pytest.fixture
def scene(conn: sqlite3.Connection, world_with_two_users: World) -> Scene:
    """Owner: live account, a second account (deleted by tests) and an archived category."""
    w = world_with_two_users
    dead = accounts_repo.create(
        conn,
        OWNER_ID,
        NewAccount(name="dead", currency="PLN", opening_balance=DEAD_OPENING),
    )
    _txn(conn, OWNER_ID, w.owner.category_id, dead.id, DEAD_EXPENSE)
    _txn(conn, OWNER_ID, w.owner.income_category_id, dead.id, DEAD_INCOME)
    old = categories_repo.create(
        conn, OWNER_ID, NewCategory(name="old", direction=Direction.EXPENSE)
    )
    _txn(conn, OWNER_ID, old.id, w.owner.account_id, ARCHIVED_CAT_EXPENSE)
    categories_repo.soft_delete(conn, OWNER_ID, old.id)
    other_dead = accounts_repo.create(
        conn, OTHER_ID, NewAccount(name="other-dead", currency="PLN", opening_balance=1_234)
    )
    _txn(conn, OTHER_ID, w.other.category_id, other_dead.id, OTHER_DEAD_EXPENSE)
    accounts_repo.soft_delete(conn, OTHER_ID, other_dead.id)
    return Scene(w, dead.id, old.id)


def _delete(conn: sqlite3.Connection, scene: Scene) -> None:
    accounts_repo.soft_delete(conn, OWNER_ID, scene.dead_account_id)


def _undo(conn: sqlite3.Connection, scene: Scene) -> None:
    accounts_repo.undelete(conn, OWNER_ID, scene.dead_account_id)


def _converter(conn: sqlite3.Connection) -> fx_svc.FxConverter:
    return fx_svc.converter_for(conn, Settings(_env_file=None), WORLD_TODAY)


def _net_worth(conn: sqlite3.Connection) -> int:
    return fortune_svc.compute_fortune(conn, OWNER_ID, _converter(conn)).net_base


def _bundle(conn: sqlite3.Connection) -> analytics_svc.AnalyticsBundle:
    return analytics_svc.bundle(conn, OWNER_ID, _converter(conn), today=WORLD_TODAY)


def _spend_total(conn: sqlite3.Connection) -> int:
    return analytics_svc.spend_total_minor(_bundle(conn))


def _budget_spent(conn: sqlite3.Connection, scene: Scene) -> int:
    summary = budget_svc.month_summary(
        conn, OWNER_ID, 2026, 11, today=WORLD_TODAY, base_currency="PLN", period_window=MONTH
    )
    line = next(ln for ln in summary.lines if ln.category_id == scene.world.owner.category_id)
    return line.spent_minor


def test_fortune_net_worth_excludes_deleted_account_and_undo_restores(
    conn: sqlite3.Connection, scene: Scene
) -> None:
    assert _net_worth(conn) == LIVE_BALANCE + DEAD_BALANCE
    _delete(conn, scene)
    assert _net_worth(conn) == LIVE_BALANCE
    _undo(conn, scene)
    assert _net_worth(conn) == LIVE_BALANCE + DEAD_BALANCE


def test_balances_list_has_only_live_accounts(conn: sqlite3.Connection, scene: Scene) -> None:
    _delete(conn, scene)
    live = accounts_repo.list_all(conn, OWNER_ID)
    balances = balance_svc.derive_balances(conn, OWNER_ID, live)
    assert balances == {scene.world.owner.account_id: LIVE_BALANCE}
    stats = balance_svc.account_stats_many(conn, OWNER_ID, live)
    assert set(stats) == {scene.world.owner.account_id}
    assert stats[scene.world.owner.account_id].balance == LIVE_BALANCE


def test_analytics_totals_exclude_deleted_account_but_keep_archived_category(
    conn: sqlite3.Connection, scene: Scene
) -> None:
    before = LIVE_EXPENSE + DEAD_EXPENSE + ARCHIVED_CAT_EXPENSE
    assert _spend_total(conn) == before
    _delete(conn, scene)
    assert _spend_total(conn) == LIVE_EXPENSE + ARCHIVED_CAT_EXPENSE  # 3_500
    nov = next(
        m for m in _bundle(conn).income_vs_expense_monthly if (m.year, m.month) == (2026, 11)
    )
    assert (nov.income_minor, nov.expense_minor) == (0, LIVE_EXPENSE + ARCHIVED_CAT_EXPENSE)
    _undo(conn, scene)
    assert _spend_total(conn) == before


def test_budget_spent_excludes_deleted_account(conn: sqlite3.Connection, scene: Scene) -> None:
    assert _budget_spent(conn, scene) == LIVE_EXPENSE + DEAD_EXPENSE
    _delete(conn, scene)
    assert _budget_spent(conn, scene) == LIVE_EXPENSE
    _undo(conn, scene)
    assert _budget_spent(conn, scene) == LIVE_EXPENSE + DEAD_EXPENSE


def test_archived_category_still_counts_in_analytics(
    conn: sqlite3.Connection, scene: Scene
) -> None:
    _delete(conn, scene)
    rows = [
        r for r in _bundle(conn).spend_by_category if r.category_id == scene.archived_category_id
    ]
    assert [r.amount_minor for r in rows] == [ARCHIVED_CAT_EXPENSE]


def test_forecast_lists_only_live_accounts(conn: sqlite3.Connection, scene: Scene) -> None:
    _delete(conn, scene)
    series = forecast_svc.forecast(
        conn, OWNER_ID, _converter(conn), WORLD_TODAY, 3, include_budget_overlay=False
    )
    day0 = series.days[0]
    assert [p.account_id for p in day0.by_account] == [scene.world.owner.account_id]
    assert day0.totals_base_minor == LIVE_BALANCE


def test_converter_currency_map_excludes_deleted_account(
    conn: sqlite3.Connection, scene: Scene
) -> None:
    assert fx_svc.currency_by_account(conn, OWNER_ID) == {
        scene.world.owner.account_id: "PLN",
        scene.dead_account_id: "PLN",
    }
    _delete(conn, scene)
    assert fx_svc.currency_by_account(conn, OWNER_ID) == {scene.world.owner.account_id: "PLN"}


def test_other_users_accounts_never_change_owner_figures(
    conn: sqlite3.Connection, scene: Scene
) -> None:
    _delete(conn, scene)
    baseline = (_net_worth(conn), _spend_total(conn), _budget_spent(conn, scene))
    accounts_repo.soft_delete(conn, OTHER_ID, scene.world.other.account_id)
    _txn(conn, OTHER_ID, scene.world.other.category_id, scene.world.other.account_id, 777)
    assert (_net_worth(conn), _spend_total(conn), _budget_spent(conn, scene)) == baseline
    assert baseline == (LIVE_BALANCE, LIVE_EXPENSE + ARCHIVED_CAT_EXPENSE, LIVE_EXPENSE)
    assert fx_svc.currency_by_account(conn, OTHER_ID) == {}
