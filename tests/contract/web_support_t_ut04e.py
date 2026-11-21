"""Pytest plugin: fixtures for the T-UT04e settings contract tests.

Re-exports the integration-web client fixtures (never the autouse
``_fast_bcrypt``: it would become session-wide) and adds an admin client,
raw clients that never attach ``X-CSRF-Token``, and a ``db`` connection on
the same scratch file. Helpers live in ``web_helpers_t_ut04e``. Never
touches ``data/budget.sqlite``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.web.app import create_app
from tests.integration.web.conftest import (
    _CSRFAwareTestClient,
    _migrated,
    anon_client,
    client,
    session_cookie,
    settings,
)

__all__ = [
    "_migrated",
    "admin_client",
    "admin_raw_client",
    "anon_client",
    "client",
    "db",
    "raw_client",
    "session_cookie",
    "settings",
]


def _promote_admin(settings_: Settings) -> None:
    conn = get_connection(settings_)
    try:
        conn.execute("UPDATE users SET is_admin = 1 WHERE id = 1")
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:
    """Autocommit-style connection on the scratch DB the clients use."""
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture
def raw_client(_migrated: Settings, session_cookie: tuple[str, str]) -> Iterator[TestClient]:
    """Signed-in client that never attaches ``X-CSRF-Token``."""
    app = create_app(settings=_migrated)
    with TestClient(app, base_url="https://testserver") as c:
        c.cookies.set(*session_cookie)
        yield c


@pytest.fixture
def admin_client(_migrated: Settings, session_cookie: tuple[str, str]) -> Iterator[TestClient]:
    """CSRF-aware client signed in as user 1 promoted to admin."""
    _promote_admin(_migrated)
    app = create_app(settings=_migrated)
    with _CSRFAwareTestClient(app) as c:
        c.cookies.set(*session_cookie)
        yield c


@pytest.fixture
def admin_raw_client(_migrated: Settings, session_cookie: tuple[str, str]) -> Iterator[TestClient]:
    """Admin client without the CSRF header (enforcement checks)."""
    _promote_admin(_migrated)
    app = create_app(settings=_migrated)
    with TestClient(app, base_url="https://testserver") as c:
        c.cookies.set(*session_cookie)
        yield c
