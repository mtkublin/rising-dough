from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from budget_planner.config import Settings
from budget_planner.db.connection import _resolve_db_path, get_connection


def _settings(tmp_path: Path, name: str = "x.sqlite") -> Settings:
    url = f"sqlite:///{(tmp_path / name).as_posix()}"
    return Settings(_env_file=None, database_url=url)


def test_resolve_db_path_rejects_non_sqlite() -> None:
    with pytest.raises(ValueError, match="sqlite"):
        _resolve_db_path("postgresql://localhost/x")


def test_get_connection_creates_parent_dir(tmp_path: Path) -> None:
    settings = _settings(tmp_path / "nested" / "deeper", "db.sqlite")
    conn = get_connection(settings)
    try:
        assert (tmp_path / "nested" / "deeper").is_dir()
    finally:
        conn.close()


def test_pragma_foreign_keys_is_on(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    conn = get_connection(settings)
    try:
        row = conn.execute("PRAGMA foreign_keys").fetchone()
        assert row[0] == 1
    finally:
        conn.close()


def test_pragma_secure_delete_is_on(tmp_path: Path) -> None:
    """ADR-0078 §6 — deleted content must be zeroed on disk, not left in free pages."""
    settings = _settings(tmp_path)
    conn = get_connection(settings)
    try:
        row = conn.execute("PRAGMA secure_delete").fetchone()
        assert row[0] == 1
    finally:
        conn.close()


def test_deleted_row_content_is_not_left_on_disk(tmp_path: Path) -> None:
    """ADR-0078 §6 — a deleted sentinel must be absent from the DB file bytes
    after a checkpoint. Checkpoint is explicit because wal_autocheckpoint = 0."""
    sentinel = "SENTINEL-T-D58-7f3a9c1e"
    db_file = tmp_path / "scratch.sqlite"
    conn = get_connection(_settings(tmp_path, "scratch.sqlite"))
    try:
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT NOT NULL)")
        conn.execute("INSERT INTO t (v) VALUES (?)", (sentinel,))
        conn.execute("DELETE FROM t")
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    finally:
        conn.close()

    assert sentinel.encode() not in db_file.read_bytes()


def test_row_factory_is_row(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    conn = get_connection(settings)
    try:
        row = conn.execute("SELECT 1 AS one").fetchone()
        assert isinstance(row, sqlite3.Row)
        assert row["one"] == 1
    finally:
        conn.close()


def test_isolation_level_none(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    conn = get_connection(settings)
    try:
        assert conn.isolation_level is None
    finally:
        conn.close()


def test_connection_usable_from_other_thread(tmp_path: Path) -> None:
    """ADR-0029: sync FastAPI dep (one anyio worker) + sync endpoint (potentially
    another worker) must be able to share one request-scoped connection without
    tripping sqlite3's thread check."""
    settings = _settings(tmp_path)
    conn = get_connection(settings)
    results: list[int | Exception] = []

    def _use_conn() -> None:
        try:
            row = conn.execute("SELECT 1 AS n").fetchone()
            results.append(int(row["n"]))
        except Exception as exc:
            results.append(exc)

    try:
        t = threading.Thread(target=_use_conn)
        t.start()
        t.join()
    finally:
        conn.close()

    assert results == [1], results
