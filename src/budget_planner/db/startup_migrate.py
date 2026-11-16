"""Apply pending migrations before the app starts (T-D19a, ADR-0071).

Invoked by the container entrypoint (``deploy/docker-entrypoint.sh``) as
``python -m budget_planner.db.startup_migrate`` right before ``exec uvicorn``.
Wraps :func:`budget_planner.db.migrate.apply_migrations` with the production
start-up policy:

- **Idempotent** — up-to-date DB → nothing written, exit 0.
- **Pre-migration backup** — when an already-initialised DB has pending
  migrations, ``VACUUM INTO`` a consistent copy under ``<db dir>/backups/``
  first; only the newest :data:`DEFAULT_KEEP_BACKUPS` are kept **and** none
  older than ``backup_max_age_days - 7`` days (T-D57, ADR-0078 §4). Pruning
  runs on every start-up, not only when a backup was just written.
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
# ADR-0078 §4: 30 d Litestream generations + 7 d noncurrent = 37 d ceiling; a
# local backup must be gone before the ceiling minus this margin.
BACKUP_AGE_MARGIN_DAYS = 7


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


def prune_backups(
    backup_dir: Path,
    db_name: str,
    keep: int,
    *,
    max_age: dt.timedelta | None = None,
    now: dt.datetime | None = None,
) -> tuple[Path, ...]:
    """Delete pre-migration backups of ``db_name`` beyond either retention rule.

    A backup is removed when it is not among the newest ``keep`` **or** (when
    ``max_age`` is given) its mtime is older than ``max_age`` before ``now``.
    Idempotent.
    """
    if not backup_dir.is_dir():
        return ()
    prefix = f"{db_name}{_BACKUP_MARKER}"
    backups = sorted(
        (p for p in backup_dir.iterdir() if p.is_file() and p.name.startswith(prefix)),
        key=lambda p: (p.stat().st_mtime_ns, p.name),
    )
    stale = set(backups[: max(len(backups) - keep, 0)])
    if max_age is not None:
        cutoff = ((now or _utcnow()) - max_age).timestamp()
        stale.update(p for p in backups if p.stat().st_mtime < cutoff)
    doomed = tuple(p for p in backups if p in stale)
    for path in doomed:
        path.unlink()
    return doomed


def backup_max_local_age(settings: Settings) -> dt.timedelta:
    """Age limit for local pre-migration backups: ceiling minus the 7 d margin."""
    return dt.timedelta(days=settings.backup_max_age_days - BACKUP_AGE_MARGIN_DAYS)


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
    pruned = prune_backups(
        db_path.parent / BACKUP_DIRNAME,
        db_path.name,
        keep_backups,
        max_age=backup_max_local_age(settings),
        now=now(),
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
