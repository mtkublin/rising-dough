"""T-D16a — multi-user migration 0012 integration tests (ADR-0061).

Covers two directions:

* ``test_0012_applies_to_v2_snapshot`` — the forward path. Hydrates a scratch
  DB from the committed v2 schema snapshot (``tests/fixtures/v2_schema_snapshot.sql``),
  seeds a handful of representative rows under ``user_id = 1``, applies
  migration 0012, and asserts the row survives, the new ``users`` columns
  land with the expected defaults, the live-email unique index exists, the
  ``user_id`` sentinel default is gone from every rebuilt table, and
  ``audit_log.actor_user_id`` is present.
* ``test_0012_down_reverses`` — the forward-smoke path. Applies 0012 on top
  of the full v2+seed, then applies the companion down script and asserts
  that the resulting schema matches a reference v2 schema produced by
  rerunning migrations 0001..0011 against a sibling scratch DB.

The v2 snapshot is the baseline both tests pin against. Regenerate it with
``scripts/dump_schema.sh`` whenever a new ``NNNN`` migration lands before 0012.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import (
    FK_OFF_MIGRATIONS,
    MIGRATIONS_DIR,
    _split_sql_statements,
    apply_migrations,
    discover,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "v2_schema_snapshot.sql"
DOWN_SQL_PATH = MIGRATIONS_DIR.parent / "migrations" / "down" / "0012_multi_user_down.sql"
# Keep absolute to the project root — MIGRATIONS_DIR is already <root>/migrations.
_DOWN_SQL_PATH_ALT = MIGRATIONS_DIR / "down" / "0012_multi_user_down.sql"


def _down_sql_file() -> Path:
    """Resolve the companion down migration regardless of layout quirks."""
    for candidate in (_DOWN_SQL_PATH_ALT, DOWN_SQL_PATH):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError("0012 down migration not found")


def _settings_for(db_path: Path) -> Settings:
    return Settings(_env_file=None, database_url=f"sqlite:///{db_path.as_posix()}")


def _apply_fixture(conn: sqlite3.Connection, sql_path: Path) -> None:
    """Hydrate the schema from a fixture dump.

    The dump is CREATE-only (schema shape, no data). ``PRAGMA foreign_keys``
    is temporarily disabled because the fixture ships tables in alphabetical
    order rather than FK-dependency order; a sibling table might not exist
    yet when the parser hits a REFERENCES clause.
    """
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript(sql_path.read_text(encoding="utf-8"))
    conn.execute("PRAGMA foreign_keys = ON")


def _snapshot_v2_schema(tmp_path: Path) -> dict[str, Any]:
    """Build a reference v2 schema by applying migrations 0001..0011 fresh."""
    staging = tmp_path / "migrations_through_11"
    staging.mkdir(parents=True, exist_ok=True)
    for mig in discover(MIGRATIONS_DIR):
        if mig.version <= 11:
            (staging / mig.filename).write_bytes(mig.sql.encode("utf-8"))
    db = tmp_path / "ref_v2.sqlite"
    conn = get_connection(_settings_for(db))
    try:
        apply_migrations(conn, staging)
        return _normalize_schema(conn)
    finally:
        conn.close()


def _normalize_schema(conn: sqlite3.Connection) -> dict[str, Any]:
    """Reduce the live schema to PRAGMA-level facts.

    Comparing raw ``sqlite_master.sql`` text is brittle: SQLite rewrites the
    stored DDL after an ``ALTER TABLE ... RENAME`` (double-quoting the table
    name, dropping redundant whitespace). Column shape, FK edges, and index
    definitions are the semantic contract — those are what we assert on.
    """
    out: dict[str, dict[str, Any]] = {}
    tables = [
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    ]
    for table in tables:
        cols = [dict(r) for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        fks = sorted(
            (dict(r) for r in conn.execute(f"PRAGMA foreign_key_list({table})").fetchall()),
            key=lambda row: (row["from"], row["table"], row["to"]),
        )
        indexes: list[dict[str, Any]] = []
        for ir in conn.execute(f"PRAGMA index_list({table})").fetchall():
            cols_in_idx = [
                dict(x) for x in conn.execute(f"PRAGMA index_info({ir['name']})").fetchall()
            ]
            indexes.append(
                {
                    "name": ir["name"],
                    "unique": ir["unique"],
                    "origin": ir["origin"],
                    "partial": ir["partial"],
                    "cols": cols_in_idx,
                }
            )
        out[table] = {
            "cols": cols,
            "fks": fks,
            "indexes": sorted(indexes, key=lambda row: row["name"]),
        }
    return out


def _apply_0012_only(conn: sqlite3.Connection) -> None:
    """Run the 0012 forward migration without the ledger machinery.

    Mirrors ``apply_migrations`` but bypasses the ``schema_migrations`` book-
    keeping — the fixture hydrates a schema-only state (no ledger rows) so we
    cannot reuse the full runner directly without first synthesising a ledger.
    FK pragma follows the real runner's behaviour: off for the body, back on
    with ``PRAGMA foreign_key_check`` after.
    """
    sql_path = MIGRATIONS_DIR / "0012_multi_user.sql"
    body = sql_path.read_text(encoding="utf-8")
    assert 12 in FK_OFF_MIGRATIONS, "runner must register 0012 for FK-off handling"
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")
    try:
        for statement in _split_sql_statements(body):
            conn.execute(statement)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        conn.execute("PRAGMA foreign_keys = ON")
        raise
    offending = conn.execute("PRAGMA foreign_key_check").fetchall()
    conn.execute("PRAGMA foreign_keys = ON")
    assert not offending, f"foreign_key_check failed after 0012: {offending}"


def _apply_0012_down(conn: sqlite3.Connection) -> None:
    """Apply the companion down migration. Mirrors FK-off handling."""
    body = _down_sql_file().read_text(encoding="utf-8")
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")
    try:
        for statement in _split_sql_statements(body):
            conn.execute(statement)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        conn.execute("PRAGMA foreign_keys = ON")
        raise
    offending = conn.execute("PRAGMA foreign_key_check").fetchall()
    conn.execute("PRAGMA foreign_keys = ON")
    assert not offending, f"foreign_key_check failed after 0012 down: {offending}"


# ---------------------------------------------------------------------------
# Fixture + seed scaffolding
# ---------------------------------------------------------------------------


def _seed_v2_rows(conn: sqlite3.Connection) -> dict[str, int]:
    """Insert the handful of rows the task spec calls for.

    Covers one account, two categories (one system-flagged, one not), two
    transactions on that account. All rows pinned to ``user_id = 1`` — the
    pre-0012 world only knew one user.
    """
    conn.execute("INSERT INTO users (id, name) VALUES (1, 'default')")

    conn.execute(
        "INSERT INTO accounts (user_id, name, currency, opening_balance) "
        "VALUES (1, 'Checking', 'PLN', 10000)"
    )
    account_id = conn.execute("SELECT id FROM accounts WHERE name = 'Checking'").fetchone()["id"]

    conn.execute(
        "INSERT INTO categories (user_id, name, direction, is_system) "
        "VALUES (1, 'Transit', 'transit', 1)"
    )
    conn.execute(
        "INSERT INTO categories (user_id, name, direction, is_system) "
        "VALUES (1, 'Groceries', 'expense', 0)"
    )
    cat_transit = conn.execute("SELECT id FROM categories WHERE name = 'Transit'").fetchone()["id"]
    cat_groceries = conn.execute("SELECT id FROM categories WHERE name = 'Groceries'").fetchone()[
        "id"
    ]

    conn.execute(
        "INSERT INTO transactions ("
        "user_id, operation_date, category_id, account_id, amount, description"
        ") VALUES (1, '2026-01-15', ?, ?, 500, 'coffee')",
        (cat_groceries, account_id),
    )
    conn.execute(
        "INSERT INTO transactions ("
        "user_id, operation_date, category_id, account_id, amount, description"
        ") VALUES (1, '2026-02-10', ?, ?, 1200, 'market')",
        (cat_groceries, account_id),
    )

    return {
        "account_id": account_id,
        "category_transit_id": cat_transit,
        "category_groceries_id": cat_groceries,
    }


# ---------------------------------------------------------------------------
# Forward test — 0012 applies against the v2 snapshot
# ---------------------------------------------------------------------------


USER_OWNED_TABLES: tuple[str, ...] = (
    "accounts",
    "categories",
    "transactions",
    "planned_transactions",
    "recurring_rules",
    "budget_defaults",
    "budget_recurring_overrides",
    "budget_one_off_overrides",
    "user_preferences",
)


def _assert_users_shape(conn: sqlite3.Connection) -> None:
    """New identity + credential columns + id=1 is unpromoted (T-D19 handles it)."""
    user_cols = {r["name"]: dict(r) for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    for col in (
        "email",
        "password_hash",
        "is_admin",
        "must_change_password",
        "updated_at",
        "deleted_at",
    ):
        assert col in user_cols, f"users.{col} must exist after 0012"
    assert user_cols["is_admin"]["notnull"] == 1
    assert user_cols["is_admin"]["dflt_value"] == "0"
    assert user_cols["must_change_password"]["notnull"] == 1
    assert user_cols["must_change_password"]["dflt_value"] == "0"

    user_row = conn.execute("SELECT * FROM users WHERE id = 1").fetchone()
    assert user_row is not None
    assert user_row["email"] is None, "pre-existing user keeps NULL email"
    assert user_row["is_admin"] == 0, "bootstrap (T-D19) is responsible for promoting the id=1 row"
    assert user_row["deleted_at"] is None
    assert user_row["password_hash"] is None


def _assert_email_index_present(conn: sqlite3.Connection) -> None:
    index_rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type = 'index' AND name = 'ux_users_email_live'"
    ).fetchall()
    assert len(index_rows) == 1, "ux_users_email_live must exist"
    index_sql = index_rows[0]["sql"]
    assert "lower(email)" in index_sql
    assert "deleted_at IS NULL" in index_sql


def _assert_sentinel_dropped(conn: sqlite3.Connection) -> None:
    for table in USER_OWNED_TABLES:
        row = next(
            r
            for r in conn.execute(f"PRAGMA table_info({table})").fetchall()
            if r["name"] == "user_id"
        )
        assert row["notnull"] == 1, f"{table}.user_id must stay NOT NULL"
        assert row["dflt_value"] is None, (
            f"{table}.user_id must have no default after 0012 (got {row['dflt_value']!r})"
        )


def _assert_audit_actor_column(conn: sqlite3.Connection) -> None:
    audit_cols = {
        r["name"]: dict(r) for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()
    }
    assert "actor_user_id" in audit_cols
    assert audit_cols["actor_user_id"]["notnull"] == 0
    actor_fk = [
        dict(r)
        for r in conn.execute("PRAGMA foreign_key_list(audit_log)").fetchall()
        if r["from"] == "actor_user_id"
    ]
    assert len(actor_fk) == 1
    assert actor_fk[0]["table"] == "users"
    assert actor_fk[0]["to"] == "id"


def _assert_seed_rows_survive(conn: sqlite3.Connection, seeded: dict[str, int]) -> None:
    n_accounts = conn.execute("SELECT COUNT(*) AS n FROM accounts").fetchone()["n"]
    n_categories = conn.execute("SELECT COUNT(*) AS n FROM categories").fetchone()["n"]
    n_transactions = conn.execute("SELECT COUNT(*) AS n FROM transactions").fetchone()["n"]
    assert n_accounts == 1
    assert n_categories == 2
    assert n_transactions == 2

    acct = conn.execute(
        "SELECT user_id, name, currency FROM accounts WHERE id = ?",
        (seeded["account_id"],),
    ).fetchone()
    assert acct["user_id"] == 1
    assert acct["name"] == "Checking"
    assert acct["currency"] == "PLN"

    groceries = conn.execute(
        "SELECT amount, description FROM transactions "
        "WHERE category_id = ? ORDER BY operation_date",
        (seeded["category_groceries_id"],),
    ).fetchall()
    assert [(r["amount"], r["description"]) for r in groceries] == [
        (500, "coffee"),
        (1200, "market"),
    ]


def test_0012_applies_to_v2_snapshot(tmp_path: Path) -> None:
    assert FIXTURE_PATH.is_file(), (
        f"missing v2 schema fixture at {FIXTURE_PATH} — regenerate with scripts/dump_schema.sh"
    )
    db = tmp_path / "fwd.sqlite"
    conn = get_connection(_settings_for(db))
    try:
        _apply_fixture(conn, FIXTURE_PATH)
        seeded = _seed_v2_rows(conn)

        # Pre-flight: the sentinel is still in place before 0012.
        pre = {r["name"]: r for r in conn.execute("PRAGMA table_info(accounts)").fetchall()}
        assert pre["user_id"]["dflt_value"] == "1", "fixture must reflect the pre-0012 world"

        _apply_0012_only(conn)

        _assert_users_shape(conn)
        _assert_email_index_present(conn)
        _assert_sentinel_dropped(conn)
        _assert_audit_actor_column(conn)
        _assert_seed_rows_survive(conn, seeded)

        offending = conn.execute("PRAGMA foreign_key_check").fetchall()
        assert not offending, f"FK check must pass after 0012: {offending}"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Down test — forward + down round-trips to the v2 schema
# ---------------------------------------------------------------------------


def test_0012_down_reverses(tmp_path: Path) -> None:
    """Forward 0012 then down should restore the pre-0012 schema shape.

    The reference is built by rerunning migrations 0001..0011 against a
    sibling scratch DB. Comparison is against the ``_normalize_schema`` facts
    (PRAGMAs), which drop cosmetic DDL rewrites SQLite does post-RENAME.
    """
    reference = _snapshot_v2_schema(tmp_path / "ref")

    db = tmp_path / "rt.sqlite"
    conn = get_connection(_settings_for(db))
    try:
        _apply_fixture(conn, FIXTURE_PATH)
        _seed_v2_rows(conn)
        _apply_0012_only(conn)
        _apply_0012_down(conn)

        actual = _normalize_schema(conn)
    finally:
        conn.close()

    # Reference includes schema_migrations (ledger table owned by 0001).
    # The fixture also ships it (see dump_schema.sh), so both snapshots
    # should contain it. Nothing else should drift.
    assert set(actual) == set(reference), (
        f"table set differs after down: "
        f"only_actual={set(actual) - set(reference)}, "
        f"only_ref={set(reference) - set(actual)}"
    )
    for table in sorted(reference):
        assert actual[table] == reference[table], (
            f"schema drift in {table} after forward+down: "
            f"actual={actual[table]!r} reference={reference[table]!r}"
        )


# ---------------------------------------------------------------------------
# T-D14 — migration 0013 adds request-ctx columns to audit_log
# ---------------------------------------------------------------------------


_REQUEST_CTX_COLUMNS: tuple[str, ...] = ("ip", "user_id", "session_id", "user_agent")


def test_0013_applies(tmp_path: Path) -> None:
    """Full forward run through 0013 adds the four request-ctx columns.

    Builds a fresh DB from migrations 0001..0013 via the real runner,
    then asserts ``audit_log`` carries the new columns in the shape
    T-D14 promises:

    * every new column is nullable;
    * ``user_id`` references ``users (id)``;
    * the other three (``ip``, ``session_id``, ``user_agent``) are plain
      scalar text/int columns with no FK.
    """
    db = tmp_path / "fwd13.sqlite"
    conn = get_connection(_settings_for(db))
    try:
        apply_migrations(conn)

        audit_cols = {
            r["name"]: dict(r) for r in conn.execute("PRAGMA table_info(audit_log)").fetchall()
        }
        for col in _REQUEST_CTX_COLUMNS:
            assert col in audit_cols, f"audit_log.{col} must exist after 0013"
            assert audit_cols[col]["notnull"] == 0, (
                f"audit_log.{col} must be nullable so historical + system rows survive"
            )
            assert audit_cols[col]["dflt_value"] is None, (
                f"audit_log.{col} must have no DEFAULT — writers always supply the value"
            )

        # user_id → users.id FK edge.
        user_id_fk = [
            dict(r)
            for r in conn.execute("PRAGMA foreign_key_list(audit_log)").fetchall()
            if r["from"] == "user_id"
        ]
        assert len(user_id_fk) == 1, "audit_log.user_id must have exactly one FK edge"
        assert user_id_fk[0]["table"] == "users"
        assert user_id_fk[0]["to"] == "id"

        # actor_user_id (added by 0012) must still be present + untouched.
        assert "actor_user_id" in audit_cols, "0013 must not remove actor_user_id (0012)"

        # A sanity write using the new columns succeeds and reads back.
        conn.execute("BEGIN")
        try:
            conn.execute(
                "INSERT INTO audit_log("
                "entity_type, entity_id, operation, prev_json, new_json, "
                "ip, user_id, session_id, user_agent"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    "mig_probe",
                    1,
                    "create",
                    None,
                    '{"x":1}',
                    "198.51.100.7",
                    1,  # seeded user via 0003
                    "sess-mig-01",
                    "mig-probe/1.0",
                ),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

        row = conn.execute(
            "SELECT ip, user_id, session_id, user_agent FROM audit_log "
            "WHERE entity_type = 'mig_probe' LIMIT 1"
        ).fetchone()
        assert row["ip"] == "198.51.100.7"
        assert row["user_id"] == 1
        assert row["session_id"] == "sess-mig-01"
        assert row["user_agent"] == "mig-probe/1.0"
    finally:
        conn.close()
