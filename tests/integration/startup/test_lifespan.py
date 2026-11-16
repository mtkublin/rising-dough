"""T-D19 — lifespan wiring of the admin bootstrap (ADR-0061 §3, ADR-0069)."""

from __future__ import annotations

import asyncio
import os
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.services import _passwords, users as users_service
from budget_planner.web.app import create_app

ADMIN_EMAIL = "ops@example.test"
ADMIN_PASSWORD = "lifespan-Init1al!"  # noqa: S105  # pragma: allowlist secret
COOKIE_SECRET = "c" * 48  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_passwords, "DEFAULT_ROUNDS", 4)


def _migrated_url(tmp_path: Path) -> str:
    url = f"sqlite:///{(tmp_path / 'lifespan.sqlite').as_posix()}"
    conn = get_connection(Settings(_env_file=None, database_url=url))
    try:
        apply_migrations(conn)
    finally:
        conn.close()
    return url


def _settings(url: str, env: str, **kwargs: Any) -> Settings:
    return Settings(
        _env_file=None,
        env=env,  # type: ignore[arg-type]
        database_url=url,
        cookie_secret=COOKIE_SECRET,
        **kwargs,
    )


def _admins(url: str) -> list[sqlite3.Row]:
    conn = get_connection(Settings(_env_file=None, database_url=url))
    try:
        return list(conn.execute("SELECT * FROM users WHERE is_admin = 1"))
    finally:
        conn.close()


def _startup_exit_code(cfg: Settings) -> object:
    """Drive the app's lifespan directly and return the ``SystemExit`` code.

    ``TestClient`` turns a ``SystemExit`` in startup into a cancelled
    portal future, so the lifespan context is entered on a plain event
    loop instead — this is what uvicorn does too.
    """
    app = create_app(settings=cfg)

    async def _enter() -> None:
        async with app.router.lifespan_context(app):
            raise AssertionError("startup did not fail")  # pragma: no cover

    # Fresh loop on a worker thread: Playwright e2e tests earlier in the
    # session can leave a running loop on the main thread.
    with ThreadPoolExecutor(max_workers=1) as pool, pytest.raises(SystemExit) as excinfo:
        pool.submit(asyncio.run, _enter()).result()
    return excinfo.value.code


def test_lifespan_calls_bootstrap_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Settings] = []
    real = users_service.bootstrap_admin_at_startup

    def _spy(cfg: Settings) -> users_service.BootstrapOutcome:
        calls.append(cfg)
        return real(cfg)

    monkeypatch.setattr(users_service, "bootstrap_admin_at_startup", _spy)
    cfg = _settings(_migrated_url(tmp_path), "test")

    with TestClient(create_app(settings=cfg)) as client:
        assert client.get("/health").status_code == 200

    assert calls == [cfg]


def test_lifespan_bootstraps_admin_from_env(tmp_path: Path) -> None:
    url = _migrated_url(tmp_path)
    cfg = _settings(url, "test", admin_email=ADMIN_EMAIL, admin_initial_password=ADMIN_PASSWORD)

    with TestClient(create_app(settings=cfg)):
        pass

    admins = _admins(url)
    assert [(r["email"], r["must_change_password"]) for r in admins] == [(ADMIN_EMAIL, 1)]
    assert _passwords.verify_password(ADMIN_PASSWORD, admins[0]["password_hash"])


def test_lifespan_exits_when_no_admin_and_env_missing(tmp_path: Path) -> None:
    cfg = _settings(_migrated_url(tmp_path), "production")

    assert _startup_exit_code(cfg) == 1


def test_lifespan_starts_with_existing_admin_and_no_env(tmp_path: Path) -> None:
    url = _migrated_url(tmp_path)
    conn = get_connection(Settings(_env_file=None, database_url=url))
    try:
        conn.execute("UPDATE users SET is_admin = 1, email = 'a@example.test' WHERE id = 1")
    finally:
        conn.close()
    cfg = _settings(url, "production", trusted_hosts="testserver")

    with TestClient(create_app(settings=cfg), base_url="https://testserver") as client:
        assert client.get("/health").status_code == 200


def test_lifespan_exits_on_unmigrated_db_in_production(tmp_path: Path) -> None:
    url = f"sqlite:///{(tmp_path / 'empty.sqlite').as_posix()}"
    conn = get_connection(Settings(_env_file=None, database_url=url))
    try:
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
    finally:
        conn.close()
    cfg = _settings(
        url, "production", admin_email=ADMIN_EMAIL, admin_initial_password=ADMIN_PASSWORD
    )

    assert _startup_exit_code(cfg) == 1


def test_uvicorn_process_exits_non_zero_without_admin_env(tmp_path: Path) -> None:
    url = _migrated_url(tmp_path)
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("BUDGET_PLANNER_ADMIN_") and k != "BUDGET_DATABASE_URL"
    }
    env.update(
        {
            "BUDGET_ENV": "production",
            "BUDGET_DATABASE_URL": url,
            "BUDGET_COOKIE_SECRET": COOKIE_SECRET,
            "PYTHONUNBUFFERED": "1",
        }
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "budget_planner.web.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            "0",
        ],
        env=env,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert proc.returncode != 0
    output = proc.stdout + proc.stderr
    assert "admin_bootstrap_failed" in output
