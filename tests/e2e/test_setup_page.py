"""First-run /setup page in a real browser (T-UR21; ADR-0134 section 9).

The shared ``live_server`` runs ``env=dev``, where a dev bootstrap admin keeps
setup closed, and seeds a login user. This module starts its own server on a
migrated DB with zero users, ``env=test`` and a configured token hash. Never
the production DB.
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
from playwright.sync_api import Browser, Page

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.services.setup import hash_token
from tests.auth_support import TEST_PASSWORD
from tests.e2e.conftest import SERVER_READY_TIMEOUT_S
from tests.ui_map import auth, rd_shell
from tests.ui_map.locator import to_playwright

pytestmark = pytest.mark.e2e

TOKEN = "-".join(("tok", "e2e", "setup", "value"))
ADMIN_EMAIL = "first.admin@example.test"
MISMATCH = "The two passwords do not match."


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_ready(url: str, proc: subprocess.Popen[bytes]) -> None:
    start = time.monotonic()
    while time.monotonic() - start < SERVER_READY_TIMEOUT_S:
        if proc.poll() is not None:
            raise RuntimeError(f"uvicorn exited with code {proc.returncode}")
        try:
            with urlopen(Request(url), timeout=2.0) as resp:  # noqa: S310  # loopback URL
                if resp.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"uvicorn did not become ready at {url}")


@pytest.fixture
def empty_server(tmp_path: Path) -> Iterator[str]:
    """uvicorn on a migrated DB with no users and an open setup token."""
    db_url = f"sqlite:///{(tmp_path / 'setup.sqlite').as_posix()}"
    conn = get_connection(Settings(_env_file=None, database_url=db_url))
    try:
        apply_migrations(conn)
    finally:
        conn.close()
    port = _free_port()
    env = os.environ.copy()
    env.update(
        BUDGET_DATABASE_URL=db_url,
        BUDGET_BIND_HOST="127.0.0.1",
        BUDGET_BIND_PORT=str(port),
        PYTHONUNBUFFERED="1",
        BUDGET_ENV="test",
        BUDGET_COOKIE_SECRET="e2e-setup-cookie-secret-not-a-real-secret-00",  # noqa: S106  # pragma: allowlist secret
        BUDGET_WEBAUTHN_RP_ID="127.0.0.1",
        BUDGET_WEBAUTHN_ORIGIN=f"http://127.0.0.1:{port}",
        BUDGET_PLANNER_SETUP_TOKEN_HASH=hash_token(TOKEN),
    )
    cmd = [sys.executable, "-m", "uvicorn", "budget_planner.web.app:app"]
    cmd += ["--host", "127.0.0.1", "--port", str(port), "--log-level", "warning"]
    proc = subprocess.Popen(  # noqa: S603  # fixed argv, no shell
        cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        _wait_ready(f"{base_url}/health", proc)
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture
def setup_page(_browser: Browser) -> Iterator[Page]:
    context = _browser.new_context()
    page = context.new_page()
    try:
        yield page
    finally:
        context.close()


def _fill(page: Page, password: str, confirm: str) -> None:
    to_playwright(page, auth.setup_name).fill("First Admin")
    to_playwright(page, auth.setup_email).fill(ADMIN_EMAIL)
    to_playwright(page, auth.setup_password).fill(password)
    to_playwright(page, auth.setup_confirm).fill(confirm)


def test_mismatch_shows_an_error_then_setup_signs_in_and_closes(
    empty_server: str, setup_page: Page
) -> None:
    page = setup_page
    page.goto(f"{empty_server}/setup?token={TOKEN}")
    to_playwright(page, auth.setup_heading).wait_for(state="visible")

    _fill(page, TEST_PASSWORD, TEST_PASSWORD + "-x")
    to_playwright(page, auth.setup_create).click()
    error = to_playwright(page, auth.setup_confirm_error)
    error.wait_for(state="visible")
    assert MISMATCH in error.inner_text()

    _fill(page, TEST_PASSWORD, TEST_PASSWORD)
    to_playwright(page, auth.setup_create).click()
    page.wait_for_url(f"{empty_server}/today")
    to_playwright(page, rd_shell.nav_desktop).wait_for(state="visible")

    # Setup is closed afterwards: the page sends the browser to sign in.
    page.goto(f"{empty_server}/setup?token={TOKEN}")
    page.context.clear_cookies()
    page.goto(f"{empty_server}/setup?token={TOKEN}")
    page.wait_for_url(f"{empty_server}/auth/login")


def test_page_is_a_404_without_the_token(empty_server: str, setup_page: Page) -> None:
    response = setup_page.goto(f"{empty_server}/setup")
    assert response is not None
    assert response.status == 404
