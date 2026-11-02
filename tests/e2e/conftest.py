"""E2E smoke-test fixtures.

Boots a real uvicorn process on an ephemeral loopback port against a
per-test migrated+seeded SQLite file, yields a Playwright page, and
tears everything down. If the Playwright browser is not installed the
whole suite is skipped with a clear message instead of crashing.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations

try:
    from playwright.sync_api import Browser, Page, Playwright, sync_playwright
except ImportError:  # pragma: no cover
    sync_playwright = None  # type: ignore[assignment]

pytestmark = pytest.mark.e2e


def strip_id_prefix(value: str | None, prefix: str) -> str:
    """Return ``value`` with ``prefix`` removed; assert ``value`` was non-None."""
    assert value is not None, f"expected an id attribute with prefix {prefix!r}"
    return value.removeprefix(prefix)


@pytest.fixture(scope="session")
def _playwright() -> Iterator[Playwright]:
    if sync_playwright is None:
        pytest.skip("playwright package not installed")
    with sync_playwright() as pw:
        yield pw


@pytest.fixture(scope="session")
def _browser(_playwright: Playwright) -> Iterator[Browser]:
    try:
        browser = _playwright.chromium.launch()
    except Exception as exc:
        pytest.skip(f"Chromium browser is not installed: {exc}")
    try:
        yield browser
    finally:
        browser.close()


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return int(port)


def _wait_until_ready(url: str, deadline_s: float = 15.0) -> None:
    start = time.monotonic()
    while time.monotonic() - start < deadline_s:
        try:
            with urlopen(Request(url), timeout=1.0) as resp:  # noqa: S310
                if resp.status == 200:
                    return
        except Exception:
            time.sleep(0.1)
    raise RuntimeError(f"uvicorn did not become ready at {url} within {deadline_s}s")


@pytest.fixture
def live_server(tmp_path: Path) -> Iterator[tuple[str, Path]]:
    """Spin uvicorn on an ephemeral port with a temp DB. Yields (base_url, db_path)."""
    db_path = tmp_path / "e2e.sqlite"
    db_url = f"sqlite:///{db_path.as_posix()}"
    port = _free_port()
    settings = Settings(_env_file=None, database_url=db_url)

    # Prime schema + seed up-front.
    conn = get_connection(settings)
    try:
        apply_migrations(conn)
    finally:
        conn.close()

    env = os.environ.copy()
    env["BUDGET_DATABASE_URL"] = db_url
    env["BUDGET_BIND_HOST"] = "127.0.0.1"
    env["BUDGET_BIND_PORT"] = str(port)
    env["PYTHONUNBUFFERED"] = "1"

    proc = subprocess.Popen(  # noqa: S603
        [
            sys.executable,
            "-m",
            "uvicorn",
            "budget_planner.web.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_until_ready(f"{base_url}/health")
        yield base_url, db_path
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture
def page(_browser: Browser) -> Iterator[Page]:
    context = _browser.new_context()
    page = context.new_page()
    try:
        yield page
    finally:
        context.close()
