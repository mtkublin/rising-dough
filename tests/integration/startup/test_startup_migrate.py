"""T-D19a — migrations applied before app start (ADR-0071)."""

from __future__ import annotations

import datetime as dt
import os
import shutil
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from structlog.testing import capture_logs

from budget_planner import logging as bp_logging
from budget_planner.config import Settings
from budget_planner.db import startup_migrate
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import MIGRATIONS_DIR, applied_versions, discover
from budget_planner.services import _passwords
from budget_planner.web.app import create_app

ADMIN_EMAIL = "ops@example.test"
ADMIN_PASSWORD = "startup-Init1al!"  # noqa: S105  # pragma: allowlist secret
COOKIE_SECRET = "s" * 48  # pragma: allowlist secret
REPO_ROOT = Path(__file__).resolve().parents[3]
ENTRYPOINT = REPO_ROOT / "deploy" / "docker-entrypoint.sh"


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_passwords, "DEFAULT_ROUNDS", 4)


def _settings(db: Path, **kwargs: Any) -> Settings:
    return Settings(_env_file=None, database_url=f"sqlite:///{db.as_posix()}", **kwargs)


def _versions(db: Path) -> set[int]:
    conn = get_connection(_settings(db))
    try:
        return set(applied_versions(conn))
    finally:
        conn.close()


def _subset_dir(tmp_path: Path, upto: int) -> Path:
    """Copy migrations ``<= upto`` into a scratch dir (simulates an older image)."""
    dest = tmp_path / f"migrations_upto_{upto:04d}"
    dest.mkdir()
    for mig in discover(MIGRATIONS_DIR):
        if mig.version <= upto:
            shutil.copy(MIGRATIONS_DIR / mig.filename, dest / mig.filename)
    return dest


def _clock(start: dt.datetime) -> Iterator[dt.datetime]:
    current = start
    while True:
        yield current
        current += dt.timedelta(seconds=1)


@pytest.fixture
def latest_version() -> int:
    return discover(MIGRATIONS_DIR)[-1].version


def test_fresh_db_applies_everything_without_backup(tmp_path: Path, latest_version: int) -> None:
    db = tmp_path / "data" / "budget.db"

    result = startup_migrate.run_startup_migrations(_settings(db))

    assert len(result.applied) == len(discover(MIGRATIONS_DIR))
    assert result.backup_path is None
    assert result.unknown_applied == ()
    assert max(_versions(db)) == latest_version
    assert not (db.parent / startup_migrate.BACKUP_DIRNAME).exists()


def test_second_run_is_a_noop(tmp_path: Path) -> None:
    db = tmp_path / "budget.db"
    startup_migrate.run_startup_migrations(_settings(db))
    before = _versions(db)

    result = startup_migrate.run_startup_migrations(_settings(db))

    assert result.applied == ()
    assert result.backup_path is None
    assert result.pruned == ()
    assert _versions(db) == before


def test_upgrade_takes_pre_migration_backup(tmp_path: Path, latest_version: int) -> None:
    db = tmp_path / "budget.db"
    older = latest_version - 1
    startup_migrate.run_startup_migrations(
        _settings(db), migrations_dir=_subset_dir(tmp_path, older)
    )

    result = startup_migrate.run_startup_migrations(_settings(db))

    assert [Path(f).name[:4] for f in result.applied] == [f"{latest_version:04d}"]
    backup = result.backup_path
    assert backup is not None
    assert backup.parent == tmp_path / "backups"
    assert backup.name.startswith(f"budget.db.pre-migrate-{older:04d}-")
    assert max(_versions(backup)) == older
    assert max(_versions(db)) == latest_version


def test_backups_are_pruned_to_keep(tmp_path: Path, latest_version: int) -> None:
    db = tmp_path / "budget.db"
    clock = _clock(dt.datetime(2026, 11, 3, 12, 0, tzinfo=dt.UTC))
    keep = 2
    first = latest_version - 3
    startup_migrate.run_startup_migrations(
        _settings(db), migrations_dir=_subset_dir(tmp_path, first)
    )
    for upto in range(first + 1, latest_version + 1):
        startup_migrate.run_startup_migrations(
            _settings(db),
            migrations_dir=_subset_dir(tmp_path, upto),
            keep_backups=keep,
            now=lambda: next(clock),
        )

    remaining = sorted(p.name for p in (tmp_path / "backups").iterdir())
    assert len(remaining) == keep
    assert remaining[-1].startswith(f"budget.db.pre-migrate-{latest_version - 1:04d}-")


def test_prune_ignores_missing_dir_and_foreign_files(tmp_path: Path) -> None:
    assert startup_migrate.prune_backups(tmp_path / "nope", "budget.db", 1) == ()
    backups = tmp_path / "backups"
    backups.mkdir()
    (backups / "notes.txt").write_text("keep me")

    assert startup_migrate.prune_backups(backups, "budget.db", 0) == ()
    assert (backups / "notes.txt").exists()


def test_schema_ahead_of_image_is_reported_not_fatal(tmp_path: Path, latest_version: int) -> None:
    db = tmp_path / "budget.db"
    startup_migrate.run_startup_migrations(_settings(db))
    older_image = _subset_dir(tmp_path, latest_version - 1)

    result = startup_migrate.run_startup_migrations(_settings(db), migrations_dir=older_image)

    assert result.applied == ()
    assert result.backup_path is None
    assert result.unknown_applied == (latest_version,)


def test_main_logs_schema_ahead_and_returns_zero(
    tmp_path: Path,
    latest_version: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bp_logging, "configure", lambda: None)
    db = tmp_path / "budget.db"
    startup_migrate.run_startup_migrations(_settings(db))
    real = startup_migrate.run_startup_migrations
    older_image = _subset_dir(tmp_path, latest_version - 1)
    monkeypatch.setattr(
        startup_migrate,
        "run_startup_migrations",
        lambda settings: real(settings, migrations_dir=older_image),
    )

    with capture_logs() as logs:
        assert startup_migrate.main(_settings(db)) == 0

    events = {e["event"]: e for e in logs}
    assert events["schema_ahead_of_image"]["unknown_versions"] == [latest_version]
    assert events["startup_migrations"]["applied"] == []


def test_main_returns_one_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bp_logging, "configure", lambda: None)
    db = tmp_path / "budget.db"
    conn = get_connection(_settings(db))
    try:
        # Corrupt bookkeeping: a schema_migrations row whose checksum does not
        # match the file on disk → the runner refuses to continue.
        conn.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
            "filename TEXT, checksum TEXT, applied_at TEXT)"
        )
        conn.execute(
            "INSERT INTO schema_migrations(version, filename, checksum) VALUES (1, 'x.sql', 'bad')"
        )
    finally:
        conn.close()

    with capture_logs() as logs:
        assert startup_migrate.main(_settings(db)) == 1

    assert [e["event"] for e in logs] == ["startup_migrations_failed"]


def test_failed_migration_leaves_db_untouched(tmp_path: Path, latest_version: int) -> None:
    db = tmp_path / "budget.db"
    older = latest_version - 1
    startup_migrate.run_startup_migrations(
        _settings(db), migrations_dir=_subset_dir(tmp_path, older)
    )
    broken = _subset_dir(tmp_path, latest_version)
    (broken / f"{latest_version + 1:04d}_broken.sql").write_text("CREATE TABLE ;")

    with pytest.raises(sqlite3.OperationalError):
        startup_migrate.run_startup_migrations(_settings(db), migrations_dir=broken)

    # The good pending migration committed; the broken one rolled back.
    assert max(_versions(db)) == latest_version


def test_production_startup_succeeds_after_startup_migrate(tmp_path: Path) -> None:
    db = tmp_path / "data" / "budget.db"
    assert startup_migrate.main(_settings(db)) == 0
    cfg = _settings(
        db,
        env="production",
        cookie_secret=COOKIE_SECRET,
        trusted_hosts="testserver",
        admin_email=ADMIN_EMAIL,
        admin_initial_password=ADMIN_PASSWORD,
    )

    with TestClient(create_app(settings=cfg), base_url="https://testserver") as client:
        assert client.get("/ready").status_code == 200

    conn = get_connection(_settings(db))
    try:
        admins = conn.execute("SELECT email FROM users WHERE is_admin = 1").fetchall()
    finally:
        conn.close()
    assert [r["email"] for r in admins] == [ADMIN_EMAIL]


def test_entrypoint_script_migrates_then_execs(tmp_path: Path, latest_version: int) -> None:
    db = tmp_path / "budget.db"
    env = {k: v for k, v in os.environ.items() if not k.startswith("BUDGET_")}
    env.update(
        {
            "BUDGET_ENV": "test",
            "BUDGET_DATABASE_URL": f"sqlite:///{db.as_posix()}",
            "PATH": f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}",
        }
    )

    proc = subprocess.run(  # noqa: S603 — fixed argv, repo-owned script
        [str(ENTRYPOINT), sys.executable, "-c", "print('exec-ok')"],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip().endswith("exec-ok")
    assert max(_versions(db)) == latest_version


def test_entrypoint_script_aborts_on_migration_failure(tmp_path: Path) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("BUDGET_")}
    env.update(
        {
            "BUDGET_ENV": "test",
            "BUDGET_DATABASE_URL": "postgres://not-supported",
            "PATH": f"{Path(sys.executable).parent}{os.pathsep}{env.get('PATH', '')}",
        }
    )

    proc = subprocess.run(  # noqa: S603 — fixed argv, repo-owned script
        [str(ENTRYPOINT), sys.executable, "-c", "print('should-not-run')"],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert proc.returncode == 1
    assert "should-not-run" not in proc.stdout
