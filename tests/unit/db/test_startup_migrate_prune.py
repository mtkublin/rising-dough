"""T-D57 / ADR-0078 §4: pre-migration backups obey count AND age rules."""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from budget_planner.config import Settings
from budget_planner.db import startup_migrate as sm

NOW = dt.datetime(2026, 11, 6, 12, 0, tzinfo=dt.UTC)
MAX_AGE = dt.timedelta(days=30)


def _make(backups: Path, n: int, age_days: float) -> Path:
    backups.mkdir(exist_ok=True)
    path = backups / f"budget.db.pre-migrate-{n:04d}-x"
    path.write_bytes(b"x")
    ts = (NOW - dt.timedelta(days=age_days)).timestamp()
    os.utime(path, (ts, ts))
    return path


def test_age_rule_removes_old_even_within_keep_count(tmp_path: Path) -> None:
    old = _make(tmp_path, 1, age_days=31)
    fresh = _make(tmp_path, 2, age_days=1)

    pruned = sm.prune_backups(tmp_path, "budget.db", 3, max_age=MAX_AGE, now=NOW)

    assert pruned == (old,)
    assert fresh.exists()


def test_count_rule_still_applies_to_young_backups(tmp_path: Path) -> None:
    files = [_make(tmp_path, i, age_days=10 - i) for i in range(5)]

    pruned = sm.prune_backups(tmp_path, "budget.db", 3, max_age=MAX_AGE, now=NOW)

    assert set(pruned) == set(files[:2])
    assert all(p.exists() for p in files[2:])


def test_backup_just_under_limit_is_kept(tmp_path: Path) -> None:
    edge = _make(tmp_path, 1, age_days=29.99)

    assert sm.prune_backups(tmp_path, "budget.db", 3, max_age=MAX_AGE, now=NOW) == ()
    assert edge.exists()


def test_prune_is_idempotent(tmp_path: Path) -> None:
    _make(tmp_path, 1, age_days=40)
    _make(tmp_path, 2, age_days=2)

    first = sm.prune_backups(tmp_path, "budget.db", 3, max_age=MAX_AGE, now=NOW)
    second = sm.prune_backups(tmp_path, "budget.db", 3, max_age=MAX_AGE, now=NOW)

    assert len(first) == 1
    assert second == ()


def test_foreign_files_are_never_pruned(tmp_path: Path) -> None:
    other = tmp_path / "notes.txt"
    other.write_text("keep")
    ts = (NOW - dt.timedelta(days=400)).timestamp()
    os.utime(other, (ts, ts))

    assert sm.prune_backups(tmp_path, "budget.db", 0, max_age=MAX_AGE, now=NOW) == ()
    assert other.exists()


def test_default_ceiling_is_37_days_and_local_limit_30() -> None:
    settings = Settings(env="test")

    assert settings.backup_max_age_days == 37
    assert sm.backup_max_local_age(settings) == dt.timedelta(days=30)


@pytest.mark.parametrize("bad", [6, 366])
def test_backup_max_age_days_bounds(bad: int) -> None:
    with pytest.raises(ValidationError):
        Settings(env="test", backup_max_age_days=bad)


def test_local_limit_follows_setting() -> None:
    settings = Settings(env="test", backup_max_age_days=14)

    assert sm.backup_max_local_age(settings) == dt.timedelta(days=7)
