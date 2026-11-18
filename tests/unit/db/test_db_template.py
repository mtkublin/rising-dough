"""The per-test template copy is indistinguishable from a fresh migration (T-CS02)."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations, discover
from tests.db_template import copy_template, sqlite_url


def _open(db_path: Path) -> sqlite3.Connection:
    return get_connection(Settings(_env_file=None, database_url=sqlite_url(db_path)))


# Seed rows carry the wall-clock time they were inserted at.
_TIMESTAMP = re.compile(r"'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?Z?'")


def _normalised_dump(conn: sqlite3.Connection) -> list[str]:
    """Full SQL dump with timestamps masked; ``schema_migrations`` as version + checksum."""
    rows = [
        _TIMESTAMP.sub("'<ts>'", line)
        for line in conn.iterdump()
        if 'INSERT INTO "schema_migrations"' not in line
    ]
    meta = conn.execute(
        "SELECT version, filename, checksum FROM schema_migrations ORDER BY version"
    ).fetchall()
    return rows + [repr(tuple(r)) for r in meta]


def test_template_copy_matches_fresh_migration(migrated_db: Path, tmp_path: Path) -> None:
    # Arrange
    fresh_path = tmp_path / "fresh" / "db.sqlite"
    fresh = _open(fresh_path)
    apply_migrations(fresh)
    copy = _open(migrated_db)

    # Act
    try:
        fresh_dump = _normalised_dump(fresh)
        copy_dump = _normalised_dump(copy)
    finally:
        fresh.close()
        copy.close()

    # Assert
    assert copy_dump == fresh_dump


def test_template_copy_has_every_migration_and_wal_mode(migrated_db: Path) -> None:
    conn = _open(migrated_db)
    try:
        versions = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert versions == {m.version for m in discover()}
        assert journal_mode == "wal"
        # Nothing left to apply: the copy is fully migrated.
        assert apply_migrations(conn) == []
    finally:
        conn.close()


def test_each_test_gets_its_own_copy(migrated_db: Path, migrated_template: Path) -> None:
    assert migrated_db != migrated_template
    conn = _open(migrated_db)
    try:
        conn.execute("CREATE TABLE scratch_only_here (x INTEGER)")
    finally:
        conn.close()
    template = sqlite3.connect(f"file:{migrated_template}?mode=ro", uri=True)
    try:
        names = {r[0] for r in template.execute("SELECT name FROM sqlite_master")}
    finally:
        template.close()
    assert "scratch_only_here" not in names


def test_copy_onto_existing_db_keeps_its_rows(migrated_template: Path, tmp_path: Path) -> None:
    # Arrange: a first fixture copied the template and wrote a row.
    dest = copy_template(migrated_template, tmp_path / "shared.sqlite")
    conn = _open(dest)
    try:
        conn.execute("CREATE TABLE written_by_first_fixture (x INTEGER)")
    finally:
        conn.close()

    # Act: a second fixture of the same test asks for a migrated DB again.
    copy_template(migrated_template, dest)

    # Assert
    conn = _open(dest)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master")}
    finally:
        conn.close()
    assert "written_by_first_fixture" in names
