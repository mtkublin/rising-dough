"""T-UR34c (ADR-0147 section 3, ADR-0148): ledger strips, planned status, override deltas.

Values are exact minor units against the frozen two-user world (today 2026-11-12); the second
user's rows never move the owner's figures.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from decimal import Decimal

from budget_planner.config import Settings
from budget_planner.domain.accounts import NewAccount
from budget_planner.domain.enums import OverrideState
from budget_planner.domain.fx import NewFxRate
from budget_planner.domain.planned import NewPlannedTransaction
from budget_planner.domain.recurring import NewRecurringOverride
from budget_planner.domain.transactions import NewTransaction
from budget_planner.repositories import (
    accounts as accounts_repo,
    fx as fx_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    transactions as txn_repo,
)
from budget_planner.services import ledger_totals as lt, preferences as preferences_svc
from budget_planner.web import ledger_data
from budget_planner.web.ledger_types import LedgerFilters, ViewKind
from tests.unit.services.conftest import OWNER_ID, WORLD_TODAY, World, expense_rule_amount

SETTINGS = Settings(_env_file=None)
EUR_PLN = Decimal("4.00")


def _ctx(
    conn: sqlite3.Connection, view: ViewKind, filters: LedgerFilters | None = None
) -> dict[str, object]:
    return ledger_data.index_context(
        conn,
        OWNER_ID,
        settings=SETTINGS,
        view=view,
        filters=filters or LedgerFilters(),
        today=WORLD_TODAY,
    )


def _planned(conn: sqlite3.Connection, w: World, user: int, day: dt.date, desc: str) -> None:
    rows = w.owner if user == OWNER_ID else w.other
    planned_repo.create(
        conn,
        user,
        NewPlannedTransaction(
            operation_date=day,
            category_id=rows.category_id,
            account_id=rows.account_id,
            amount=100,
            description=desc,
        ),
    )


def test_planned_strip_counts_and_row_status(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    _planned(conn, w, OWNER_ID, dt.date(2026, 11, 5), "late-7")
    _planned(conn, w, OWNER_ID, dt.date(2026, 11, 9), "late-3")
    _planned(conn, w, OWNER_ID, WORLD_TODAY, "today")
    _planned(conn, w, w.other.user_id, dt.date(2026, 11, 1), "other-late")
    ctx = _ctx(conn, "planned")
    summary = ctx["planned_summary"]
    assert isinstance(summary, lt.PlannedTotals)
    assert (summary.count, summary.overdue_count, summary.due_today_count) == (4, 2, 1)
    rows = ctx["rows"]
    assert isinstance(rows, list)
    status = {r["description"]: r["status"] for r in rows}
    assert status["late-7"] == lt.PlannedStatus(lt.PlannedStatusKind.OVERDUE, 7)
    assert status["late-3"] == lt.PlannedStatus(lt.PlannedStatusKind.OVERDUE, 3)
    assert status["today"] == lt.PlannedStatus(lt.PlannedStatusKind.DUE_TODAY, 0)
    assert status["planned-1"] == lt.PlannedStatus(lt.PlannedStatusKind.IN_DAYS, 1)
    assert "other-late" not in status


def test_actual_spent_converts_eur_and_excludes_other_month_income_and_other_user(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    fx_repo.upsert_rate(
        conn, NewFxRate(date=WORLD_TODAY, from_ccy="EUR", to_ccy="PLN", rate=EUR_PLN)
    )
    eur = accounts_repo.create(
        conn, OWNER_ID, NewAccount(name="eur", currency="EUR", opening_balance=0)
    )

    def add(account: int, cat: int, day: dt.date, amount: int, user: int = OWNER_ID) -> None:
        txn_repo.create(
            conn,
            user,
            NewTransaction(operation_date=day, category_id=cat, account_id=account, amount=amount),
        )

    add(w.owner.account_id, w.owner.category_id, dt.date(2026, 11, 11), 2_450)
    add(eur.id, w.owner.category_id, dt.date(2026, 11, 12), 30_000)  # 120_000 PLN
    add(w.owner.account_id, w.owner.category_id, dt.date(2026, 10, 31), 9_999)  # last month
    add(w.owner.account_id, w.owner.income_category_id, dt.date(2026, 11, 11), 50_000)  # income
    add(w.other.account_id, w.other.category_id, dt.date(2026, 11, 11), 7_777, w.other.user_id)
    # the 11 Nov income opens the pay window, so the world's 10 Nov expense (1_000) is before it:
    # 2_450 + 30_000 EUR * 4.00
    assert _ctx(conn, "actual")["spent_minor"] == 122_450


def test_actual_spent_is_none_without_cached_rate(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    eur = accounts_repo.create(
        conn, OWNER_ID, NewAccount(name="eur", currency="EUR", opening_balance=0)
    )
    txn_repo.create(
        conn,
        OWNER_ID,
        NewTransaction(
            operation_date=WORLD_TODAY, category_id=w.owner.category_id, account_id=eur.id, amount=5
        ),
    )
    assert _ctx(conn, "actual")["spent_minor"] is None


def test_recurring_strip_and_override_delta(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    rule_amount = expense_rule_amount(OWNER_ID)  # 700
    for day, amount in (
        (dt.date(2026, 11, 15), rule_amount + 150),
        (dt.date(2026, 12, 15), rule_amount - 200),
    ):
        recurring_repo.upsert_override(
            conn,
            OWNER_ID,
            NewRecurringOverride(
                rule_id=w.owner.rule_id,
                occurrence_date=day,
                state=OverrideState.OVERRIDDEN,
                amount_override=amount,
            ),
        )
    ctx = _ctx(conn, "recurring")
    summary = ctx["recurring_summary"]
    assert isinstance(summary, lt.RecurringTotals)
    # next-due override 850 out (the effective amount), income 5_000 in, both monthly
    assert (summary.rule_count, summary.next_due) == (2, dt.date(2026, 11, 15))
    assert (summary.monthly_in_minor, summary.monthly_out_minor, summary.net_minor) == (
        5_000,
        850,
        4_150,
    )
    rows = ctx["rows"]
    assert isinstance(rows, list)
    deltas = next(r for r in rows if r["id"] == w.owner.rule_id)["override_deltas"]
    assert deltas == {
        dt.date(2026, 11, 15): lt.OverrideDelta(150, lt.DeltaDirection.UP),
        dt.date(2026, 12, 15): lt.OverrideDelta(200, lt.DeltaDirection.DOWN),
    }


def test_override_delta_same_and_status_boundaries() -> None:
    assert lt.override_delta(700, 700) == lt.OverrideDelta(0, lt.DeltaDirection.SAME)
    in_45 = lt.planned_status(WORLD_TODAY + dt.timedelta(days=45), WORLD_TODAY)
    assert in_45 == lt.PlannedStatus(lt.PlannedStatusKind.IN_DAYS, 45)


def test_filter_summary_names_active_filters(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    w = world_with_two_users
    filters = LedgerFilters(
        category_ids=(w.owner.category_id,),
        account_ids=(w.owner.account_id, w.other.account_id),  # other user's id is skipped
        direction="expense",
        search="pizza",
        date_from=dt.date(2026, 1, 1),
        date_to=dt.date(2026, 1, 31),
    )
    summary = _ctx(conn, "actual", filters)["filter_summary"]
    assert summary == ledger_data.FilterSummary(
        category_names=("cat-1",),
        account_names=("acct-1",),
        direction="expense",
        search="pizza",
        date_from=dt.date(2026, 1, 1),
        date_to=dt.date(2026, 1, 31),
    )
    assert isinstance(summary, ledger_data.FilterSummary)
    assert summary.is_active
    empty = _ctx(conn, "actual")["filter_summary"]
    assert isinstance(empty, ledger_data.FilterSummary)
    assert not empty.is_active


def test_actual_spent_uses_the_pay_window_not_the_calendar_month(
    conn: sqlite3.Connection, world_with_two_users: World
) -> None:
    """ADR-0151 section 2: income anchor on 25 Oct, today 3 Nov: spent counts 25 Oct..today."""
    w = world_with_two_users
    preferences_svc.set_income_anchor_category_id(conn, OWNER_ID, w.owner.income_category_id)

    def add(cat: int, day: dt.date, amount: int, *, user: int = OWNER_ID) -> None:
        rows = w.owner if user == OWNER_ID else w.other
        txn_repo.create(
            conn,
            user,
            NewTransaction(
                operation_date=day, category_id=cat, account_id=rows.account_id, amount=amount
            ),
        )

    add(w.owner.income_category_id, dt.date(2026, 10, 25), 100_000)  # payday opens the window
    add(w.owner.category_id, dt.date(2026, 10, 24), 5_000)  # before the window
    add(w.owner.category_id, dt.date(2026, 10, 25), 1_100)
    add(w.owner.category_id, dt.date(2026, 10, 30), 2_200)  # previous calendar month, in window
    add(w.owner.category_id, dt.date(2026, 11, 3), 330)
    add(w.other.category_id, dt.date(2026, 10, 30), 7_777, user=w.other.user_id)
    spent = ledger_data.period_spent_minor(conn, OWNER_ID, SETTINGS, dt.date(2026, 11, 3))
    # 1_100 + 2_200 + 330, plus the world's own 1_000 expense dated 10 Nov (inside the window)
    assert spent == 4_630
