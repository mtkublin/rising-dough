"""T-D60 — retention purge of audit ip/user_agent and ended sessions (ADR-0078 §7)."""

from __future__ import annotations

import asyncio
import datetime as dt
import sqlite3
import threading
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from structlog.testing import capture_logs

from budget_planner.config import Settings
from budget_planner.db import retention as retention_cli
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.services import retention
from budget_planner.web import retention_task

NOW = dt.datetime(2026, 11, 6, 12, 0, 0, tzinfo=dt.UTC)
FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


def _ts(days: float) -> str:
    return (NOW - dt.timedelta(days=days)).strftime(FMT)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(_env_file=None, database_url=f"sqlite:///{(tmp_path / 't.sqlite').as_posix()}")


@pytest.fixture
def conn(settings: Settings) -> sqlite3.Connection:
    c = get_connection(settings)
    apply_migrations(c)
    return c


def _audit(conn: sqlite3.Connection, age_days: float, ip: str | None = "1.2.3.4") -> int:
    cur = conn.execute(
        "INSERT INTO audit_log (entity_type, entity_id, changed_at, operation, ip, user_agent) "
        "VALUES ('x', 1, ?, 'create', ?, ?)",
        (_ts(age_days), ip, "UA" if ip else None),
    )
    assert cur.lastrowid is not None
    return cur.lastrowid


def _user(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO users (name, email, password_hash) VALUES ('r', 'r@x.test', 'h')"
    )
    assert cur.lastrowid is not None
    return cur.lastrowid


def _session(
    conn: sqlite3.Connection, sid: str, expires_days: float, revoked_days: float | None = None
) -> None:
    conn.execute(
        "INSERT INTO sessions (id, user_id, expires_at, revoked_at, ip, user_agent, "
        "authenticated_at) VALUES (?, ?, ?, ?, '1.1.1.1', 'UA', ?)",
        (
            sid,
            _user(conn),
            _ts(expires_days),
            None if revoked_days is None else _ts(revoked_days),
            _ts(200),
        ),
    )


def test_audit_boundary_90_89_91(conn: sqlite3.Connection, settings: Settings) -> None:
    exact, young, old = _audit(conn, 90), _audit(conn, 89), _audit(conn, 91)

    result = retention.purge(conn, NOW, settings)

    ips = {r["id"]: r["ip"] for r in conn.execute("SELECT id, ip FROM audit_log")}
    assert ips == {exact: "1.2.3.4", young: "1.2.3.4", old: None}
    assert result.audit_rows_scrubbed == 1
    uas = {r["id"]: r["user_agent"] for r in conn.execute("SELECT id, user_agent FROM audit_log")}
    assert uas[old] is None and uas[exact] == "UA"


def test_audit_rows_are_never_deleted(conn: sqlite3.Connection, settings: Settings) -> None:
    _audit(conn, 400)
    retention.purge(conn, NOW, settings)
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 1


def test_sessions_boundary_and_live_untouched(conn: sqlite3.Connection, settings: Settings) -> None:
    _session(conn, "live", expires_days=-10)  # expires in the future
    _session(conn, "expired_old", expires_days=91)
    _session(conn, "expired_89", expires_days=89)
    _session(conn, "expired_90", expires_days=90)
    _session(conn, "revoked_old", expires_days=-10, revoked_days=100)
    _session(conn, "revoked_recent", expires_days=-10, revoked_days=5)

    result = retention.purge(conn, NOW, settings)

    left = {r["id"] for r in conn.execute("SELECT id FROM sessions")}
    assert left == {"live", "expired_89", "expired_90", "revoked_recent"}
    assert result.sessions_deleted == 2


def test_purge_is_idempotent(conn: sqlite3.Connection, settings: Settings) -> None:
    _audit(conn, 120)
    _session(conn, "old", expires_days=120)
    first = retention.purge(conn, NOW, settings)
    second = retention.purge(conn, NOW, settings)
    assert (first.audit_rows_scrubbed, first.sessions_deleted) == (1, 1)
    assert (second.audit_rows_scrubbed, second.sessions_deleted) == (0, 0)


def test_custom_retention_days(conn: sqlite3.Connection, tmp_path: Path) -> None:
    cfg = Settings(
        _env_file=None,
        database_url=f"sqlite:///{(tmp_path / 'c.sqlite').as_posix()}",
        retention_personal_days=30,
    )
    _audit(conn, 31)
    assert retention.purge(conn, NOW, cfg).audit_rows_scrubbed == 1


def test_logs_counts_only(conn: sqlite3.Connection, settings: Settings) -> None:
    _audit(conn, 120, ip="9.9.9.9")
    with capture_logs() as logs:
        retention.purge(conn, NOW, settings)
    rec = next(r for r in logs if r["event"] == "retention_purge")
    assert rec["audit_rows_scrubbed"] == 1
    assert "9.9.9.9" not in repr(logs)


@pytest.mark.parametrize("days", [6, 3651])
def test_setting_validator_rejects_out_of_range(days: int) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, retention_personal_days=days)


def test_default_is_90() -> None:
    assert Settings(_env_file=None).retention_personal_days == 90


def test_cli_main_purges_scratch_db(settings: Settings) -> None:
    c = get_connection(settings)
    apply_migrations(c)
    old = _audit(c, 1000)
    c.close()
    assert retention_cli.main(settings) == 0
    c = get_connection(settings)
    assert c.execute("SELECT ip FROM audit_log WHERE id=?", (old,)).fetchone()["ip"] is None
    c.close()


def test_cli_main_returns_1_on_failure(tmp_path: Path) -> None:
    # Unmigrated DB: tables are missing, so the purge fails; failure is non-fatal exit 1.
    cfg = Settings(_env_file=None, database_url=f"sqlite:///{(tmp_path / 'e.sqlite').as_posix()}")
    assert retention_cli.main(cfg) == 1


def _run_in_thread(factory: Callable[[], Coroutine[Any, Any, None]]) -> None:
    """Run a coroutine on a fresh loop in its own thread (isolated from any ambient loop)."""
    errors: list[BaseException] = []

    def target() -> None:
        try:
            asyncio.run(factory())
        except BaseException as exc:  # surfaced below
            errors.append(exc)

    worker = threading.Thread(target=target)
    worker.start()
    worker.join(timeout=30)
    assert not worker.is_alive()
    if errors:
        raise errors[0]


def test_background_loop_runs_and_survives_errors(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    calls: list[int] = []
    done = threading.Event()

    def fake_run(cfg: Settings) -> None:
        calls.append(1)
        if len(calls) >= 2:
            done.set()
        if len(calls) == 1:
            raise RuntimeError("boom")

    monkeypatch.setattr(retention_cli, "run", fake_run)

    async def scenario() -> None:
        task = asyncio.create_task(retention_task.run_forever(settings, 0.01))
        await asyncio.wait_for(asyncio.to_thread(done.wait), timeout=10)
        await retention_task.stop(task)
        assert task.done()

    _run_in_thread(scenario)
    assert len(calls) >= 2


def test_start_creates_cancellable_task(settings: Settings) -> None:
    async def scenario() -> None:
        task = retention_task.start(settings)
        await retention_task.stop(task)
        assert task.done()

    _run_in_thread(scenario)


def test_mixed_timestamp_formats_near_boundary(
    conn: sqlite3.Connection, settings: Settings
) -> None:
    """Space separator, offsets and Z compare correctly (cutoff 2026-08-08 12:00 UTC)."""
    cases = {
        "2026-08-08 11:59:59": True,
        "2026-08-08 12:00:01": False,
        "2026-08-08T11:59:59+00:00": True,
        "2026-08-08T13:59:59+02:00": True,  # == 11:59:59 UTC
        "2026-08-08T12:00:01Z": False,
    }
    ids: dict[str, int | None] = {}
    for stamp in cases:
        cur = conn.execute(
            "INSERT INTO audit_log (entity_type, entity_id, changed_at, operation, ip) "
            "VALUES ('x', 1, ?, 'create', '1.1.1.1')",
            (stamp,),
        )
        ids[stamp] = cur.lastrowid
        _session(conn, f"s-{stamp}", expires_days=0)
        conn.execute("UPDATE sessions SET expires_at = ? WHERE id = ?", (stamp, f"s-{stamp}"))

    retention.purge(conn, NOW, settings)

    for stamp, purged in cases.items():
        ip = conn.execute("SELECT ip FROM audit_log WHERE id = ?", (ids[stamp],)).fetchone()["ip"]
        session = conn.execute("SELECT 1 FROM sessions WHERE id = ?", (f"s-{stamp}",)).fetchone()
        assert (ip is None) is purged, stamp
        assert (session is None) is purged, stamp
