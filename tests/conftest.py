"""Root pytest conftest — environment pinning for the suite.

Pytest imports ``budget_planner.web.app`` through transitive imports in
most test modules. That module instantiates ``create_app()`` which in
turn calls ``get_settings()``. Under the default (``BUDGET_ENV=dev``)
the config emits a ``UserWarning`` about the dev cookie-secret fallback,
and the pytest ``filterwarnings = ["error"]`` policy turns that into a
collection-time error.

Pin ``BUDGET_ENV=test`` at import time so test runs stay quiet. Tests
that need to assert on dev / production behaviour override via
``monkeypatch`` in their own body.
"""

from __future__ import annotations

import os

# G10: unconditional (not setdefault): an inherited BUDGET_ENV=prod must never reach the suite.
os.environ["BUDGET_ENV"] = "test"

# Imported after the env pin: ``tests.db_template`` pulls in the app config.
import functools
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import fastapi.dependencies.utils as fastapi_dependency_utils
import pytest

from tests.db_template import build_template, copy_template

# T-CS08: every web test builds a fresh app, and FastAPI re-analyses every
# endpoint signature on that app's first request (~35% of ~87 ms CPU per app).
# The analysis is a pure function of the endpoint callable, so cache it for the
# test process. Production keeps FastAPI's own behaviour.
fastapi_dependency_utils.get_typed_signature = functools.cache(
    fastapi_dependency_utils.get_typed_signature
)


_PROD_DB = (Path(__file__).resolve().parents[1] / "data" / "budget.sqlite").resolve()
_REAL_CONNECT = sqlite3.connect


def _is_prod_db(database: object) -> bool:
    if not isinstance(database, str | Path):
        return False
    target = str(database)
    return not target.startswith(("file:", ":memory:")) and Path(target).resolve() == _PROD_DB


def _guarded_connect(database: Any, *args: Any, **kwargs: Any) -> sqlite3.Connection:
    """G10 tripwire: refuse ``<repo>/data/budget.sqlite`` (cwd-independent, any spelling)."""
    if _is_prod_db(database):
        raise RuntimeError(
            "tests must never open the production database data/budget.sqlite "
            "(CLAUDE.md Databases, ADR-0130 G10)"
        )
    connection: sqlite3.Connection = _REAL_CONNECT(database, *args, **kwargs)
    return connection


@pytest.fixture(scope="session", autouse=True)
def _prod_db_tripwire() -> Iterator[None]:
    """G10: wrap ``sqlite3.connect`` for the session so no test can open the production file."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(sqlite3, "connect", _guarded_connect)
        yield


@pytest.fixture(scope="session")
def migrated_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One fully migrated DB per pytest process (T-CS02); copy, never open it."""
    return build_template(tmp_path_factory.mktemp("template") / "migrated.sqlite")


@pytest.fixture
def migrated_db(migrated_template: Path, tmp_path: Path) -> Path:
    """Path to this test's own copy of the migrated template (``tmp_path/db.sqlite``)."""
    return copy_template(migrated_template, tmp_path / "db.sqlite")
