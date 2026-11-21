"""Migrations round-trip integration test.

Confirms every migration applies cleanly to an empty DB, the system seed
lands, and the schema migrations ledger refuses to re-apply.
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path

import pytest

from budget_planner import clock
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import MIGRATIONS_DIR, apply_migrations, discover
from budget_planner.domain.system_categories import (
    RECONCILIATION_CATEGORY_NAME,
    TRANSIT_CATEGORY_NAME,
)

pytestmark = pytest.mark.integration


EXPECTED_TABLES = {
    "accounts",
    "account_snapshots",
    "audit_log",
    "budget_defaults",
    "budget_one_off_overrides",
    "budget_recurring_overrides",
    "categories",
    "fx_rates",
    "planned_transactions",
    "recurring_rule_overrides",
    "recurring_rules",
    "schema_migrations",
    "transactions",
    "users",
}


def _settings_for(tmp_path: Path) -> Settings:
    db = (tmp_path / "db.sqlite").as_posix()
    return Settings(_env_file=None, database_url=f"sqlite:///{db}")


def test_migrate_from_empty_db_creates_all_tables(tmp_path: Path) -> None:
    settings = _settings_for(tmp_path)
    conn = get_connection(settings)
    try:
        apply_migrations(conn)
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        table_names = {r["name"] for r in rows}
        assert EXPECTED_TABLES.issubset(table_names)
    finally:
        conn.close()


def test_migrate_is_idempotent_when_run_twice(tmp_path: Path) -> None:
    settings = _settings_for(tmp_path)
    conn = get_connection(settings)
    try:
        apply_migrations(conn)
        apply_migrations(conn)  # second application: no-op, no exception.
        count = conn.execute("SELECT COUNT(*) AS n FROM schema_migrations").fetchone()["n"]
        assert count >= 3  # at least schema_meta, core_schema, seed
    finally:
        conn.close()


def test_seed_migration_inserts_system_rows(conn: sqlite3.Connection) -> None:
    user_count = conn.execute("SELECT COUNT(*) AS n FROM users WHERE id=1").fetchone()["n"]
    assert user_count == 1

    system_names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM categories WHERE is_system=1 AND deleted_at IS NULL"
        ).fetchall()
    }
    assert TRANSIT_CATEGORY_NAME in system_names
    assert RECONCILIATION_CATEGORY_NAME in system_names


def test_audit_log_empty_after_seed(conn: sqlite3.Connection) -> None:
    """Seeds bypass audit by design (ADR-0019 — schema facts, not user actions)."""
    n = conn.execute("SELECT COUNT(*) AS n FROM audit_log").fetchone()["n"]
    assert n == 0


# ---------------------------------------------------------------------------
# T-117 / ADR-0038 — post-apply shape of the recurring schema
# ---------------------------------------------------------------------------
def test_recurring_rules_next_due_is_not_null_after_apply(tmp_path: Path) -> None:
    """0006 + backfill + 0007 land `next_due NOT NULL` on a fresh DB."""
    settings = _settings_for(tmp_path)
    conn = get_connection(settings)
    try:
        apply_migrations(conn)
        rows = conn.execute("PRAGMA table_info(recurring_rules)").fetchall()
        by_name = {r["name"]: r for r in rows}
        assert "next_due" in by_name
        assert by_name["next_due"]["notnull"] == 1
        assert "last_promoted_date" in by_name
        assert by_name["last_promoted_date"]["notnull"] == 0
    finally:
        conn.close()


def test_transactions_grows_recurring_provenance_columns_and_index(tmp_path: Path) -> None:
    """0006 adds both provenance columns + the composite index."""
    settings = _settings_for(tmp_path)
    conn = get_connection(settings)
    try:
        apply_migrations(conn)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(transactions)").fetchall()}
        assert "promoted_from_recurring_rule_id" in cols
        assert "promoted_from_recurring_date" in cols
        indexes = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='transactions'"
            ).fetchall()
        }
        assert "ix_transactions_promoted_from_recurring" in indexes
    finally:
        conn.close()


def test_backfill_populates_next_due_for_preexisting_rules(tmp_path: Path) -> None:
    """Pre-insert a rule between 0005 and 0006 to exercise the Python hook.

    This simulates upgrading a dev DB that already has recurring rules
    predating ADR-0038. We apply migrations 0001-0005 by filtering the
    discovered list, insert fixture rows, then apply the remaining
    migrations and assert the backfill picked up the right `next_due`.
    """
    settings = _settings_for(tmp_path)
    conn = get_connection(settings)
    try:
        # Apply only migrations <= 0005 by staging them into a tmp dir.
        staging = tmp_path / "migrations_partial"
        staging.mkdir()
        for mig in discover(MIGRATIONS_DIR):
            if mig.version <= 5:
                (staging / mig.filename).write_bytes(mig.sql.encode("utf-8"))
        apply_migrations(conn, staging)

        today = clock.utc_now().date()
        # Rule A: start_date in the past, no end_date → next_due should be
        # the first monthly occurrence on-or-after today (anchored on the
        # start_date's day-of-month). Users row (id=1) is already seeded
        # by migration 0003; we only need the account + category.
        past_start = today - dt.timedelta(days=90)
        conn.execute("INSERT INTO accounts(name, currency) VALUES ('A', 'PLN')")
        conn.execute("INSERT INTO categories(name, direction) VALUES ('Rent', 'expense')")
        account_id = conn.execute("SELECT id FROM accounts WHERE name='A'").fetchone()["id"]
        category_id = conn.execute("SELECT id FROM categories WHERE name='Rent'").fetchone()["id"]
        conn.execute(
            "INSERT INTO recurring_rules("
            "cadence, start_date, category_id, account_id, default_amount, active) "
            "VALUES ('monthly', ?, ?, ?, 10000, 1)",
            (past_start.isoformat(), category_id, account_id),
        )
        # Rule B: end_date already passed → backfill deactivates + sentinel.
        past_end = today - dt.timedelta(days=30)
        past_start_b = today - dt.timedelta(days=400)
        conn.execute(
            "INSERT INTO recurring_rules("
            "cadence, start_date, end_date, category_id, account_id, default_amount, active) "
            "VALUES ('monthly', ?, ?, ?, ?, 5000, 1)",
            (past_start_b.isoformat(), past_end.isoformat(), category_id, account_id),
        )

        # Now apply all remaining migrations (0006 + backfill hook + 0007).
        apply_migrations(conn, MIGRATIONS_DIR)

        rules = conn.execute(
            "SELECT id, start_date, end_date, active, next_due FROM recurring_rules ORDER BY id ASC"
        ).fetchall()
        assert len(rules) == 2

        rule_a, rule_b = rules
        # Rule A — next_due is a date on or after today.
        next_due_a = dt.date.fromisoformat(rule_a["next_due"])
        assert next_due_a >= today
        # Monthly cadence anchored on `past_start.day` — next_due must land
        # within one month of today's day roll.
        assert (next_due_a - today).days <= 32
        assert rule_a["active"] == 1

        # Rule B — end_date passed, so deactivated + sentinel = start_date.
        assert rule_b["active"] == 0
        assert dt.date.fromisoformat(rule_b["next_due"]) == past_start_b
    finally:
        conn.close()


def test_backfill_is_idempotent_on_rerun(tmp_path: Path) -> None:
    """Re-running apply_migrations after a prior full apply is a no-op."""
    settings = _settings_for(tmp_path)
    conn = get_connection(settings)
    try:
        apply_migrations(conn)
        before = conn.execute(
            "SELECT COUNT(*) AS n FROM recurring_rules WHERE next_due IS NULL"
        ).fetchone()["n"]
        # No pre-existing rules on a fresh seed; backfill is still a no-op.
        assert before == 0
        apply_migrations(conn)  # second run — hook does not fire (already applied).
        after = conn.execute(
            "SELECT COUNT(*) AS n FROM recurring_rules WHERE next_due IS NULL"
        ).fetchone()["n"]
        assert after == 0
    finally:
        conn.close()
