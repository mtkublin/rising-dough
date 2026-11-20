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

os.environ.setdefault("BUDGET_ENV", "test")

# Imported after the env pin: ``tests.db_template`` pulls in the app config.
import functools
from pathlib import Path

import fastapi.dependencies.utils as fastapi_dependency_utils
import pytest

from tests.db_template import build_template, copy_template
from tests.e2e.mockup_target import pytest_addoption as _mockup_addoption

# T-CS08: every web test builds a fresh app, and FastAPI re-analyses every
# endpoint signature on that app's first request (~35% of ~87 ms CPU per app).
# The analysis is a pure function of the endpoint callable, so cache it for the
# test process. Production keeps FastAPI's own behaviour.
fastapi_dependency_utils.get_typed_signature = functools.cache(
    fastapi_dependency_utils.get_typed_signature
)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register ``--target`` (T-UT09) for every test; the e2e fixtures read it."""
    _mockup_addoption(parser)


@pytest.fixture(scope="session")
def migrated_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One fully migrated DB per pytest process (T-CS02); copy, never open it."""
    return build_template(tmp_path_factory.mktemp("template") / "migrated.sqlite")


@pytest.fixture
def migrated_db(migrated_template: Path, tmp_path: Path) -> Path:
    """Path to this test's own copy of the migrated template (``tmp_path/db.sqlite``)."""
    return copy_template(migrated_template, tmp_path / "db.sqlite")
