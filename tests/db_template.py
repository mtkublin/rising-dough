"""Migrated template DB, copied per test (T-CS02, ADR-0108 §2).

Running every migration for each of ~1,500 DB-backed tests dominated the
suite's setup time. Instead the schema is migrated once per pytest
process (each xdist worker builds its own) and each test gets a byte copy
of that file. ``get_connection`` re-applies the per-connection pragmas, so
the copy behaves exactly like a freshly migrated DB;
``tests/unit/db/test_db_template.py`` proves the two are identical.

Tests that exercise the migration runner itself keep calling
``apply_migrations`` directly.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations

_SQLITE_PREFIX = "sqlite:///"


def sqlite_url(db_path: Path) -> str:
    return f"{_SQLITE_PREFIX}{db_path.as_posix()}"


def db_path_of(settings: Settings) -> Path:
    """The file behind ``settings.database_url`` (``sqlite:///`` only)."""
    if not settings.database_url.startswith(_SQLITE_PREFIX):
        raise ValueError(f"not a sqlite URL: {settings.database_url!r}")
    return Path(settings.database_url.removeprefix(_SQLITE_PREFIX))


def build_template(db_path: Path) -> Path:
    """Migrate a fresh DB at ``db_path`` and fold the WAL into the main file."""
    conn = get_connection(Settings(_env_file=None, database_url=sqlite_url(db_path)))
    try:
        apply_migrations(conn)
        # wal_autocheckpoint is 0 (ADR-0034 §2): checkpoint explicitly so
        # the main file alone holds the whole schema.
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    finally:
        conn.close()
    wal = db_path.with_name(db_path.name + "-wal")
    if wal.exists() and wal.stat().st_size > 0:
        raise RuntimeError(f"template WAL not empty after checkpoint: {wal}")
    return db_path


def copy_template(template: Path, dest: Path) -> Path:
    """Make ``dest`` a migrated DB and return it.

    A missing ``dest`` gets a copy of ``template``. An existing one (another
    fixture of the same test got there first, maybe already writing rows) is
    migrated in place instead, so a second fixture never wipes the first one's
    data — the same idempotence ``apply_migrations`` had.
    """
    if dest.exists():
        conn = get_connection(Settings(_env_file=None, database_url=sqlite_url(dest)))
        try:
            apply_migrations(conn)
        finally:
            conn.close()
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(template, dest)
    return dest
