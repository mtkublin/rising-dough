"""Shared fixtures for visual-regression tests (ADR-0027 §4).

The suite is opt-in: it is excluded from the default `pytest` run via the
`-m "not visual"` default marker expression and from CI unless
`CI_VISUAL=1`. The `just test-visual` recipe runs it; `just test-visual-update`
regenerates baselines after an intentional design change.
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

VISUAL_ROOT = Path(__file__).parent
BASELINES = VISUAL_ROOT / "baselines"
REPO_ROOT = VISUAL_ROOT.parents[1]
DEMO_DB = REPO_ROOT / "data" / "demo.sqlite"
# demo.sqlite's newest transaction is 2026-10-31; pin the server clock there so
# "today"-relative UI (fiscal period, days left, overdue tint) is stable (T-VIS5).
FROZEN_DATE = "2026-10-31"


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
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                try:
                    if httpx.get(f"{base}/health", timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    time.sleep(0.2)
            else:
                raise RuntimeError(f"uvicorn did not come up on {base}")
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
