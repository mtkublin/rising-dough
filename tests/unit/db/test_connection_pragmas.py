"""Verify every PRAGMA ADR-0034 §2 requires lands on a fresh connection.

Bypassing :func:`get_connection` and talking to SQLite directly would drop
``wal_autocheckpoint = 0`` on the floor and silently break Litestream
replication. This test is the floor on that invariant.
"""

from __future__ import annotations

from pathlib import Path

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection


def _settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, database_url=f"sqlite:///{(tmp_path / 'x.sqlite').as_posix()}")


def test_journal_mode_is_wal(tmp_path: Path) -> None:
    conn = get_connection(_settings(tmp_path))
    try:
        row = conn.execute("PRAGMA journal_mode;").fetchone()
        assert row[0].lower() == "wal"
    finally:
        conn.close()


def test_synchronous_is_normal(tmp_path: Path) -> None:
    conn = get_connection(_settings(tmp_path))
    try:
        # NORMAL == 1 per https://sqlite.org/pragma.html#pragma_synchronous
        row = conn.execute("PRAGMA synchronous;").fetchone()
        assert row[0] == 1
    finally:
        conn.close()


def test_wal_autocheckpoint_is_zero(tmp_path: Path) -> None:
    """ADR-0034 §2 — Litestream owns checkpoint cadence. Any non-zero value
    here is a bug that can silently truncate WAL frames Litestream has not
    yet shipped to the bucket."""
    conn = get_connection(_settings(tmp_path))
    try:
        row = conn.execute("PRAGMA wal_autocheckpoint;").fetchone()
        assert row[0] == 0
    finally:
        conn.close()


def test_busy_timeout_is_5000ms(tmp_path: Path) -> None:
    conn = get_connection(_settings(tmp_path))
    try:
        row = conn.execute("PRAGMA busy_timeout;").fetchone()
        assert row[0] == 5000
    finally:
        conn.close()


def test_foreign_keys_is_on(tmp_path: Path) -> None:
    conn = get_connection(_settings(tmp_path))
    try:
        row = conn.execute("PRAGMA foreign_keys;").fetchone()
        assert row[0] == 1
    finally:
        conn.close()
