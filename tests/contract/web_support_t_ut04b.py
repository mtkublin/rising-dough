"""Pytest plugin: fixtures for the T-UT04b contract tests (today, accounts).

Re-exports the integration-web client fixtures (authenticated, anonymous,
CSRF-aware) so contract tests run on the same temp-DB harness, and adds a raw
client that never attaches ``X-CSRF-Token``. Loaded with ``pytest_plugins``;
helpers live in ``web_helpers_t_ut04b`` (importing them here would defeat
assertion rewriting). Never re-export an autouse fixture: it would apply to
the whole session. Never touches the production database.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.web.app import create_app
from tests.integration.web.conftest import (
    _migrated,
    anon_client,
    client,
    session_cookie,
    settings,
)

__all__ = [
    "_migrated",
    "anon_client",
    "client",
    "raw_client",
    "session_cookie",
    "settings",
]


@pytest.fixture
def raw_client(_migrated: Settings, session_cookie: tuple[str, str]) -> Iterator[TestClient]:
    """Signed-in client that never attaches ``X-CSRF-Token`` (CSRF enforcement)."""
    app = create_app(settings=_migrated)
    with TestClient(app, base_url="https://testserver") as c:
        c.cookies.set(*session_cookie)
        yield c
