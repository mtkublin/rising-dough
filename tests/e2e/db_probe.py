"""Read-only probes of the scratch e2e database (ADR-0106: assert the DB effect).

Journeys seed through HTTP and then look ids up here instead of scraping them
out of markup. Only ever opened on the per-test ``live_server`` scratch file.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def rows(db_path: Path, sql: str, *params: Any) -> list[tuple[Any, ...]]:
    """Run a read-only query against the scratch DB."""
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        return [tuple(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def scalar(db_path: Path, sql: str, *params: Any) -> Any:
    found = rows(db_path, sql, *params)
    assert len(found) == 1 and len(found[0]) == 1, f"expected one scalar, got {found!r}"
    return found[0][0]


def account_id(db_path: Path, name: str) -> int:
    return int(
        scalar(db_path, "SELECT id FROM accounts WHERE name = ? AND deleted_at IS NULL", name)
    )


def category_id(db_path: Path, name: str) -> int:
    return int(
        scalar(db_path, "SELECT id FROM categories WHERE name = ? AND deleted_at IS NULL", name)
    )


def txn_id(db_path: Path, description: str) -> int:
    return int(
        scalar(
            db_path,
            "SELECT id FROM transactions WHERE description = ? AND deleted_at IS NULL",
            description,
        )
    )


def txn_amounts(db_path: Path, description: str) -> list[int]:
    """Minor-unit amounts of live transactions with ``description`` (oldest first)."""
    found = rows(
        db_path,
        "SELECT amount FROM transactions WHERE description = ? AND deleted_at IS NULL ORDER BY id",
        description,
    )
    return [int(r[0]) for r in found]


def planned_id(db_path: Path, description: str) -> int:
    return int(
        scalar(
            db_path,
            "SELECT id FROM planned_transactions WHERE description = ? AND deleted_at IS NULL",
            description,
        )
    )


def rule_id(db_path: Path, description: str) -> int:
    return int(
        scalar(
            db_path,
            "SELECT id FROM recurring_rules WHERE default_description = ? AND deleted_at IS NULL",
            description,
        )
    )
