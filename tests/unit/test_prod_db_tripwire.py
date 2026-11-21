"""T-Q231: a test that sets no DB URL must never resolve into the repo data directory."""

from __future__ import annotations

import os
from pathlib import Path

from budget_planner.config import Settings
from tests.db_template import db_path_of

_REPO_DATA_DIR = (Path(__file__).resolve().parents[2] / "data").resolve()


def test_default_settings_do_not_resolve_to_prod_db() -> None:
    resolved = db_path_of(Settings()).resolve()

    assert resolved.parent != _REPO_DATA_DIR


def test_admin_bootstrap_env_is_unset_for_the_suite() -> None:
    leaked = sorted(k for k in os.environ if k.startswith("BUDGET_PLANNER_ADMIN_"))

    assert leaked == []
