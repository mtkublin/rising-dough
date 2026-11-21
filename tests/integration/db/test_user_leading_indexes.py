"""T-Q205 / Q-034: hot user-scoped queries use ``user_id``-leading indexes.

The SQL is captured from the repository functions via the connection trace
callback (no SQL duplicated here), then ``EXPLAIN QUERY PLAN`` is asserted:
the main table is reached through a SEARCH on the named index, never a SCAN.
The audit-by-user read has no repository function yet, so that one statement
is the spec (``repro/C/explain_plans.py``).
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from datetime import date

import pytest

from budget_planner.domain.planned import PlannedFilter
from budget_planner.domain.transactions import TransactionFilter
from budget_planner.repositories import (
    planned as planned_repo,
    recurring as recurring_repo,
    transactions as txn_repo,
)

pytestmark = pytest.mark.integration

USER_ID = 1
AUDIT_BY_USER_SQL = "SELECT * FROM audit_log WHERE user_id = 1 ORDER BY id DESC LIMIT 50"
_FIRST_TABLE = re.compile(r"^(SCAN|SEARCH) (\S+)(?: USING (?:COVERING )?INDEX (\S+))?")


def _captured_selects(conn: sqlite3.Connection, run: Callable[[], object]) -> list[str]:
    seen: list[str] = []
    conn.set_trace_callback(seen.append)
    try:
        run()
    finally:
        conn.set_trace_callback(None)
    return [s for s in seen if s.lstrip().upper().startswith("SELECT") and "FROM" in s.upper()]


def _plan_main_access(conn: sqlite3.Connection, sql: str, table_or_alias: str) -> tuple[str, str]:
    """Return (SCAN|SEARCH, index name or '') for the named table/alias."""
    for row in conn.execute("EXPLAIN QUERY PLAN " + sql).fetchall():
        match = _FIRST_TABLE.match(row[3])
        if match and match.group(2) == table_or_alias:
            return match.group(1), match.group(3) or ""
    raise AssertionError(f"no plan row for {table_or_alias}")


def _assert_index(conn: sqlite3.Connection, sql: str, table: str, index: str) -> None:
    kind, used = _plan_main_access(conn, sql, table)
    assert (kind, used) == ("SEARCH", index), sql


def test_transactions_list_uses_user_date_index(conn: sqlite3.Connection) -> None:
    flt = TransactionFilter(
        date_from=date(2026, 11, 1), date_to=date(2026, 11, 30), order_desc=True, limit=50
    )
    sqls = _captured_selects(conn, lambda: txn_repo.list_filtered(conn, USER_ID, flt))
    assert sqls
    _assert_index(conn, sqls[-1], "t", "ix_transactions_user_live_date")


def test_transactions_newest_first_uses_user_date_index(conn: sqlite3.Connection) -> None:
    flt = TransactionFilter(order_desc=True, limit=50)
    sqls = _captured_selects(conn, lambda: txn_repo.list_filtered(conn, USER_ID, flt))
    _assert_index(conn, sqls[-1], "t", "ix_transactions_user_live_date")


def test_planned_list_uses_user_date_index(conn: sqlite3.Connection) -> None:
    flt = PlannedFilter()
    sqls = _captured_selects(conn, lambda: planned_repo.list_filtered(conn, USER_ID, flt))
    _assert_index(conn, sqls[-1], "p", "ix_planned_user_live_date")


@pytest.mark.parametrize("active_only", [True, False])
def test_recurring_rules_use_user_active_index(conn: sqlite3.Connection, active_only: bool) -> None:
    sqls = _captured_selects(
        conn, lambda: recurring_repo.list_rules(conn, USER_ID, active_only=active_only)
    )
    _assert_index(conn, sqls[-1], "recurring_rules", "ix_recurring_user_active")


def test_audit_by_user_uses_user_id_index(conn: sqlite3.Connection) -> None:
    _assert_index(conn, AUDIT_BY_USER_SQL, "audit_log", "ix_audit_user_id")
