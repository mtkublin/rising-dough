"""T-D01 — /health and /ready endpoints.

Both routes stay public (no auth; mounted before any auth middleware).
/health is a cheap process-liveness probe. /ready exercises SQLite via
PRAGMA integrity_check and surfaces failures as 503.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.web.app import create_app


@pytest.fixture
def health_client(tmp_path: Path) -> TestClient:
    db_url = f"sqlite:///{(tmp_path / 'health.sqlite').as_posix()}"
    cfg = Settings(_env_file=None, database_url=db_url)
    conn = get_connection(cfg)
    try:
        apply_migrations(conn)
    finally:
        conn.close()
    return TestClient(create_app(settings=cfg))


def test_health_returns_200_and_version(health_client: TestClient) -> None:
    r = health_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["version"]  # non-empty


def test_ready_returns_200_when_db_is_fine(health_client: TestClient) -> None:
    r = health_client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body == {"status": "ready", "db": "ok"}


def test_ready_returns_503_when_db_path_is_bogus(tmp_path: Path) -> None:
    """Point the DB URL at an unusable path and assert the readiness
    probe reports 503 with a diagnostic body shape.

    ``/dev/null`` is a character device — SQLite opens it as an empty DB
    but ``PRAGMA integrity_check`` on a non-DB file reports a diagnostic
    non-"ok" row, which is what readiness exists to catch.
    """
    cfg = Settings(_env_file=None, database_url="sqlite:////dev/null")
    client = TestClient(create_app(settings=cfg))
    r = client.get("/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready"
    assert "detail" in body


def test_health_does_not_touch_db(tmp_path: Path) -> None:
    """A bogus DB URL must not break /health — the whole point is to be
    cheap and DB-free."""
    cfg = Settings(_env_file=None, database_url="sqlite:////nonexistent/path.db")
    client = TestClient(create_app(settings=cfg))
    r = client.get("/health")
    assert r.status_code == 200
