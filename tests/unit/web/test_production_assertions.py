"""T-D04 — in production the lifespan must fail fast on wrong PRAGMAs.

The helper under test is :func:`budget_planner.web.app._assert_production_pragmas`.
It is a no-op in dev / test and raises in production when the DB file's
``wal_autocheckpoint`` is anything other than 0.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Literal

import pytest

import budget_planner.web.app as app_mod
from budget_planner.config import Settings
from budget_planner.web.app import _assert_production_pragmas


def _settings(tmp_path: Path, *, env: Literal["dev", "test", "production"]) -> Settings:
    db_path = tmp_path / "budget.sqlite"
    return Settings(
        _env_file=None,
        env=env,
        database_url=f"sqlite:///{db_path.as_posix()}",
        cookie_secret="unit-test-secret",  # pragma: allowlist secret  # noqa: S106
    )


def test_noop_in_dev(tmp_path: Path) -> None:
    """Dev / test envs must not touch the DB."""
    cfg = _settings(tmp_path, env="dev")
    # The DB file does not exist yet — the helper must not try to open it.
    _assert_production_pragmas(cfg)
    assert not (tmp_path / "budget.sqlite").exists()


def test_noop_in_test(tmp_path: Path) -> None:
    cfg = _settings(tmp_path, env="test")
    _assert_production_pragmas(cfg)
    assert not (tmp_path / "budget.sqlite").exists()


def test_passes_in_production_with_correct_pragmas(tmp_path: Path) -> None:
    """``get_connection`` already sets ``wal_autocheckpoint = 0``, so a
    fresh DB opened via our factory passes the assertion."""
    cfg = _settings(tmp_path, env="production")
    _assert_production_pragmas(cfg)  # does not raise


def test_fails_in_production_when_pragma_drifts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate a connection factory that silently flips
    ``wal_autocheckpoint`` back on (the bypass the docstring warns
    against). The helper must reject the DB."""
    db_path = tmp_path / "budget.sqlite"

    def _bad_factory(_cfg: Settings) -> sqlite3.Connection:
        c = sqlite3.connect(db_path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA wal_autocheckpoint = 1000;")
        return c

    monkeypatch.setattr(app_mod, "get_connection", _bad_factory)

    cfg = _settings(tmp_path, env="production")
    with pytest.raises(RuntimeError, match="wal_autocheckpoint must be 0"):
        _assert_production_pragmas(cfg)
