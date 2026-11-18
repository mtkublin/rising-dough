"""Shared fixtures for service-layer unit tests (temp DB + schema + seeds)."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from tests.db_template import sqlite_url


@pytest.fixture
def conn(migrated_db: Path) -> Iterator[sqlite3.Connection]:
    settings = Settings(_env_file=None, database_url=sqlite_url(migrated_db))
    c = get_connection(settings)
    try:
        yield c
    finally:
        c.close()
