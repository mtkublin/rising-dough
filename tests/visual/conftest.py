"""Shared fixtures for visual-regression tests (ADR-0027 §4).

The suite is excluded from the default `pytest` run via the `-m "not visual"`
default marker expression, so laptop runs never compare macOS rendering. It runs
in `.github/workflows/visual.yml` and, locally, through `just visual` (pinned
Playwright container, ADR-0027 amendment 2026-11-22, T-Q251). `just visual-update`
regenerates the baselines inside the same container.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import Browser, sync_playwright

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.web.auth_cookies import SESSION_DEV_COOKIE_NAME
from tests.auth_support import issue_session, seed_login_user
from tests.visual.frozen_server import HANDOFF_FIXTURE_DATE

VISUAL_ROOT = Path(__file__).parent
# Linux baselines, generated only in the pinned Playwright container (ADR-0027, T-Q251).
BASELINES = VISUAL_ROOT / "__snapshots__"
REPO_ROOT = VISUAL_ROOT.parents[1]
DEMO_DB = REPO_ROOT / "data" / "demo.sqlite"
# demo.sqlite's newest transaction is 2026-10-31; pin the server clock there so
# "today"-relative UI (fiscal period, days left, overdue tint) is stable (T-VIS5).
FROZEN_DATE = HANDOFF_FIXTURE_DATE


# Deterministic text raster: no GPU tiling, no LCD/subpixel glyph positioning,
# no hinting drift between runs (T-VIS2 flake fix).
CHROMIUM_STABLE_ARGS = [
    "--disable-gpu",
    "--disable-lcd-text",
    "--font-render-hinting=none",
    "--disable-font-subpixel-positioning",
    "--force-color-profile=srgb",
    "--disable-skia-runtime-opts",
]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--reference",
        default=None,
        choices=["handoff"],
        help="compare against the designer-handoff references (T-UT10, ADR-0106)",
    )
    parser.addoption(
        "--surface",
        default=None,
        help="limit --reference=handoff to one surface (today, ledger, plan, ...)",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """With ``--reference=handoff`` run only the reference comparisons."""
    if config.getoption("--reference") != "handoff":
        return
    keep = [i for i in items if "test_reference" in i.nodeid]
    config.hook.pytest_deselected(items=[i for i in items if i not in keep])
    items[:] = keep


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="session")
def scratch_db(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, str]:
    """Copy ``data/demo.sqlite`` (or start empty) into a temp file, migrate it,
    and give user 1 a password + live session (T-D02b).

    Never touches ``data/budget.sqlite`` (prod). Returns ``(path, session id)``.
    """
    path = tmp_path_factory.mktemp("visual") / "visual.sqlite"
    if DEMO_DB.exists():
        shutil.copyfile(DEMO_DB, path)
    settings = Settings(_env_file=None, database_url=f"sqlite:///{path.as_posix()}")
    conn = get_connection(settings)
    try:
        apply_migrations(conn)
        seed_login_user(conn)
        session_id = issue_session(conn)
    finally:
        conn.close()
    return path, session_id


SERVER_READY_TIMEOUT_S = float(os.environ.get("VISUAL_SERVER_READY_TIMEOUT_S", "120"))


def _wait_until_ready(url: str, proc: subprocess.Popen[bytes]) -> None:
    """Poll ``url`` until it answers 200; fail fast if the server process died (T-Q248 pattern)."""
    deadline = time.monotonic() + SERVER_READY_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"uvicorn exited with code {proc.returncode} before {url} was ready")
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise RuntimeError(f"uvicorn did not become ready at {url} within {SERVER_READY_TIMEOUT_S}s")


@pytest.fixture(scope="session")
def live_server(scratch_db: tuple[Path, str]) -> Iterator[str]:
    """Boot uvicorn against a scratch copy of the demo DB for the session.

    Routes the server at `127.0.0.1:<free-port>`. Blocks until `/health`
    returns 200 or raises after a 45 s timeout (cold `uv run` start can take >10 s).
    """
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        "BUDGET_DATABASE_URL": f"sqlite:///{scratch_db[0].as_posix()}",
        # Plain HTTP → dev cookie names without ``Secure`` (ADR-0065/0070).
        "BUDGET_ENV": "dev",
        "BUDGET_VISUAL_FROZEN_DATE": FROZEN_DATE,
        # pragma: allowlist nextline secret
        "BUDGET_COOKIE_SECRET": "visual-dev-cookie-secret-not-a-real-secret",
    }
    cmd = ["uv", "run", "python", "-m", "tests.visual.frozen_server", str(port)]
    with subprocess.Popen(cmd, env=env) as proc:  # noqa: S603 — fixed args, local loopback port
        try:
            _wait_until_ready(f"{base}/health", proc)
            yield base
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


@pytest.fixture(scope="session")
def browser() -> Iterator[Browser]:
    with sync_playwright() as p:
        b = p.chromium.launch(args=CHROMIUM_STABLE_ARGS)
        try:
            yield b
        finally:
            b.close()


@pytest.fixture(scope="session")
def session_cookies(live_server: str, scratch_db: tuple[Path, str]) -> list[dict[str, str]]:
    """Playwright ``add_cookies`` payload that signs the browser in as user 1."""
    return [{"name": SESSION_DEV_COOKIE_NAME, "value": scratch_db[1], "url": live_server}]


@pytest.fixture()
def update_baseline() -> bool:
    return bool(os.environ.get("VISUAL_UPDATE"))


@pytest.fixture()
def baselines_dir() -> Path:
    return BASELINES
