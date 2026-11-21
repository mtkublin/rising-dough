"""Shared fixtures and helpers for the shell / auth / errors contract tests.

Re-exports the CSRF-aware, session-aware web-test clients from
``tests/integration/web/conftest.py`` (T-D02b, T-D08) so contract tests run
on the same app wiring, plus a ``db`` connection on the same scratch file and
small audit-log helpers. The autouse ``_fast_bcrypt`` fixture is NOT re-exported
(a plugin would apply it session-wide); ``tests/contract/conftest.py`` supplies a
contract-scoped one. Never points at the production database.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator

import pytest

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from tests.integration.web.conftest import (  # noqa: F401
    _migrated,
    admin_client,
    anon_client,
    client,
    session_cookie,
    settings,
)

ANON_STATUSES = frozenset({302, 303})


@pytest.fixture
def db(_migrated: Settings) -> Iterator[sqlite3.Connection]:  # noqa: F811
    """Connection to the same scratch DB the ``client`` fixtures use."""
    conn = get_connection(_migrated)
    try:
        yield conn
    finally:
        conn.close()
