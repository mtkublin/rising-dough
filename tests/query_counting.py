"""T-Q234: SQL statement counting for web routes (``assert_max_queries``).

Counts every statement executed on the per-request connection opened by
``web.deps.get_db`` via ``sqlite3.Connection.set_trace_callback``.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection

_NOISE = re.compile(r"^\s*(PRAGMA|BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE)", re.IGNORECASE)


@contextmanager
def count_statements(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Collect each non-noise SQL statement run on request connections."""
    log: list[str] = []

    def counting(settings: Settings) -> sqlite3.Connection:
        conn = get_connection(settings)
        conn.set_trace_callback(lambda sql: log.append(sql) if not _NOISE.match(sql) else None)
        return conn

    monkeypatch.setattr("budget_planner.web.deps.get_connection", counting)
    yield log


def make_assert_max_queries(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> Callable[[str, int], int]:
    """Return ``assert_max_queries(route, n)``: GET ``route`` (200) in <= n statements."""

    def assert_max_queries(route: str, n: int) -> int:
        with count_statements(monkeypatch) as log:
            resp = client.get(route)
        assert resp.status_code == 200, (route, resp.status_code)
        assert len(log) <= n, f"{route}: {len(log)} statements > budget {n}"
        return len(log)

    return assert_max_queries
