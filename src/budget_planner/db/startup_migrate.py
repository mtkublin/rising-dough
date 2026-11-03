"""Apply pending migrations before the app starts (T-D19a, ADR-0071).

Invoked by the container entrypoint (``deploy/docker-entrypoint.sh``) as
``python -m budget_planner.db.startup_migrate`` right before ``exec uvicorn``.
Wraps :func:`budget_planner.db.migrate.apply_migrations` with the production
start-up policy:

- **Idempotent** — up-to-date DB → nothing written, exit 0.
- **Pre-migration backup** — when an already-initialised DB has pending
  migrations, ``VACUUM INTO`` a consistent copy under ``<db dir>/backups/``
  first; only the newest :data:`DEFAULT_KEEP_BACKUPS` are kept.
- **Schema ahead of image** — versions recorded in the DB that this image
  does not ship (rollback onto a newer schema) are logged and tolerated,
  per the N-1 compatibility policy in ADR-0071 §4.
- **Fail fast** — any error exits 1 so uvicorn never starts on a half-way
  schema (each migration is its own transaction, so the DB is unchanged).
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from budget_planner import logging as bp_logging
from budget_planner.config import Settings, get_settings
from budget_planner.db.connection import _resolve_db_path, get_connection
from budget_planner.db.migrate import (
    MIGRATIONS_DIR,
    Migration,
    applied_versions,
    apply_migrations,
    discover,
)

DEFAULT_KEEP_BACKUPS = 3
BACKUP_DIRNAME = "backups"
_BACKUP_MARKER = ".pre-migrate-"


@dataclass(frozen=True, slots=True, kw_only=True)
class MigrationPlan:
    """What a start-up run would do against the current DB state."""

    pending: tuple[Migration, ...]
    applied: tuple[int, ...]
    unknown_applied: tuple[int, ...]

    @property
    def needs_backup(self) -> bool:
        """Back up only when there is existing schema AND something to apply."""
        return bool(self.pending) and bool(self.applied)


@dataclass(frozen=True, slots=True, kw_only=True)
class StartupMigrationResult:
    applied: tuple[str, ...]
    backup_path: Path | None
    pruned: tuple[Path, ...]
    unknown_applied: tuple[int, ...]


def plan_migrations(
    conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR
) -> MigrationPlan:
    """Compare on-disk migrations with the DB's ``schema_migrations``."""
    available = discover(migrations_dir)
    known = {m.version for m in available}
    applied = applied_versions(conn)
    return MigrationPlan(
        pending=tuple(m for m in available if m.version not in applied),
        applied=tuple(sorted(applied)),
        unknown_applied=tuple(sorted(v for v in applied if v not in known)),
    )


def backup_path_for(db_path: Path, last_applied: int, now: dt.datetime) -> Path:
    """``<dir>/backups/<name>.pre-migrate-<NNNN>-<UTC ts>``."""
    stamp = now.astimezone(dt.UTC).strftime("%Y%m%dT%H%M%S%fZ")
    name = f"{db_path.name}{_BACKUP_MARKER}{last_applied:04d}-{stamp}"
    return db_path.parent / BACKUP_DIRNAME / name


def backup_database(conn: sqlite3.Connection, dest: Path) -> Path:
    """Write a consistent single-file copy of ``conn``'s DB to ``dest``.

    ``VACUUM INTO`` reads one snapshot through the existing connection, so
    no second writer is opened against the live file (ADR-0034 §2).
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    conn.execute("VACUUM INTO ?", (str(dest),))
    return dest


def prune_backups(backup_dir: Path, db_name: str, keep: int) -> tuple[Path, ...]:
    """Delete all but the newest ``keep`` pre-migration backups of ``db_name``."""
    if not backup_dir.is_dir():
        return ()
    prefix = f"{db_name}{_BACKUP_MARKER}"
    backups = sorted(
        (p for p in backup_dir.iterdir() if p.is_file() and p.name.startswith(prefix)),
        key=lambda p: (p.stat().st_mtime_ns, p.name),
    )
    stale = tuple(backups[: max(len(backups) - keep, 0)])
    for path in stale:
        path.unlink()
    return stale


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def run_startup_migrations(
    settings: Settings,
    *,
    migrations_dir: Path = MIGRATIONS_DIR,
    keep_backups: int = DEFAULT_KEEP_BACKUPS,
    now: Callable[[], dt.datetime] = _utcnow,
) -> StartupMigrationResult:
    """Back up if needed, apply pending migrations, prune old backups."""
    db_path = _resolve_db_path(settings.database_url)
    conn = get_connection(settings)
    try:
        plan = plan_migrations(conn, migrations_dir)
        backup = (
            backup_database(conn, backup_path_for(db_path, plan.applied[-1], now()))
            if plan.needs_backup
            else None
        )
        applied = apply_migrations(conn, migrations_dir)
    finally:
        conn.close()
    pruned = (
        prune_backups(db_path.parent / BACKUP_DIRNAME, db_path.name, keep_backups)
        if backup is not None
        else ()
    )
    return StartupMigrationResult(
        applied=tuple(m.filename for m in applied),
        backup_path=backup,
        pruned=pruned,
        unknown_applied=plan.unknown_applied,
    )


def main(settings: Settings | None = None) -> int:
    """CLI entrypoint. Returns the process exit code (0 ok, 1 failure)."""
    bp_logging.configure()
    log = bp_logging.get_logger("budget_planner.startup_migrate")
    try:
        result = run_startup_migrations(settings or get_settings())
    except Exception as exc:  # any failure must block startup
        log.error("startup_migrations_failed", error=str(exc), error_type=type(exc).__name__)
        return 1
    if result.unknown_applied:
        log.warning("schema_ahead_of_image", unknown_versions=list(result.unknown_applied))
    log.info(
        "startup_migrations",
        applied=list(result.applied),
        backup=str(result.backup_path) if result.backup_path else None,
        pruned=[str(p) for p in result.pruned],
    )
    return 0


if __name__ == "__main__":  # pragma: no cover — exercised via the entrypoint
    raise SystemExit(main())
