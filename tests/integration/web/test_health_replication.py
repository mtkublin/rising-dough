"""T-D144 / ADR-0119: GET /health/replication."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.web.app import create_app


def _client(tmp_path: Path, status_file: str) -> TestClient:
    db_url = f"sqlite:///{(tmp_path / 'r.sqlite').as_posix()}"
    cfg = Settings(_env_file=None, database_url=db_url, replication_status_file=status_file)
    conn = get_connection(cfg)
    try:
        apply_migrations(conn)
    finally:
        conn.close()
    return TestClient(create_app(settings=cfg))


def _write(path: Path, *, newest_age: timedelta, error: str | None = None) -> None:
    now = datetime.now(UTC)
    path.write_text(
        json.dumps(
            {
                "checked_at": now.isoformat(),
                "newest_object_at": (now - newest_age).isoformat(),
                "generation": "abc123",
                "error": error,
            }
        ),
        encoding="utf-8",
    )


def test_disabled_without_status_file_is_200(tmp_path: Path) -> None:
    r = _client(tmp_path, "").get("/health/replication")
    assert r.status_code == 200
    assert r.json()["status"] == "disabled"


def test_fresh_is_200_and_public_json(tmp_path: Path) -> None:
    f = tmp_path / "status.json"
    _write(f, newest_age=timedelta(hours=1))
    r = _client(tmp_path, str(f)).get("/health/replication", follow_redirects=False)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["status"] == "ok"
    assert r.json()["generation"] == "abc123"


def test_stale_is_503(tmp_path: Path) -> None:
    f = tmp_path / "status.json"
    _write(f, newest_age=timedelta(hours=30))
    r = _client(tmp_path, str(f)).get("/health/replication")
    assert (r.status_code, r.json()["status"]) == (503, "stale")


def test_missing_file_is_503(tmp_path: Path) -> None:
    r = _client(tmp_path, str(tmp_path / "nope.json")).get("/health/replication")
    assert (r.status_code, r.json()["status"]) == (503, "missing")


def test_unreadable_path_is_503(tmp_path: Path) -> None:
    r = _client(tmp_path, str(tmp_path)).get("/health/replication")  # a directory
    assert (r.status_code, r.json()["status"]) == (503, "unreadable")


def test_probe_error_is_503(tmp_path: Path) -> None:
    f = tmp_path / "status.json"
    _write(f, newest_age=timedelta(minutes=1), error="generations_failed")
    r = _client(tmp_path, str(f)).get("/health/replication")
    assert (r.status_code, r.json()["status"]) == (503, "probe_error")


def test_head_matches_get_when_disabled(tmp_path: Path) -> None:
    client = _client(tmp_path, "")
    r = client.head("/health/replication")
    assert r.status_code == client.get("/health/replication").status_code == 200
    assert r.content == b""


def test_head_matches_get_when_fresh(tmp_path: Path) -> None:
    f = tmp_path / "status.json"
    _write(f, newest_age=timedelta(hours=1))
    client = _client(tmp_path, str(f))
    r = client.head("/health/replication")
    assert r.status_code == client.get("/health/replication").status_code == 200
    assert r.content == b""


def test_head_is_503_when_stale(tmp_path: Path) -> None:
    f = tmp_path / "status.json"
    _write(f, newest_age=timedelta(hours=30))
    client = _client(tmp_path, str(f))
    r = client.head("/health/replication")
    assert r.status_code == client.get("/health/replication").status_code == 503
    assert r.content == b""


def test_head_is_503_when_status_file_missing(tmp_path: Path) -> None:
    client = _client(tmp_path, str(tmp_path / "nope.json"))
    r = client.head("/health/replication")
    assert r.status_code == client.get("/health/replication").status_code == 503
    assert r.content == b""
