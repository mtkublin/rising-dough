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
from budget_planner.web.auth_cookies import SESSION_DEV_COOKIE_NAME
from budget_planner.web.middleware.csrf import (
    CSRF_DEV_COOKIE_NAME,
    CSRF_FORM_FIELD,
    CSRF_HEADER_NAME,
)
from tests.auth_support import TEST_EMAIL, TEST_PASSWORD, seed_login_user

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

    # Prime schema + seed up-front. T-D02b: give user 1 a login so the
    # ``page`` fixture can sign in through the real /auth/login form.
    conn = get_connection(settings)
    try:
        apply_migrations(conn)
        seed_login_user(conn)
    finally:
        conn.close()

    env = os.environ.copy()
    env["BUDGET_DATABASE_URL"] = db_url
    env["BUDGET_BIND_HOST"] = "127.0.0.1"
    env["BUDGET_BIND_PORT"] = str(port)
    env["PYTHONUNBUFFERED"] = "1"
    # T-D08 — e2e runs over plain HTTP (http://127.0.0.1:port); the browser
    # rejects ``Secure`` cookies on HTTP, which breaks the CSRF
    # double-submit flow. ``env=dev`` suppresses the ``Secure`` flag.
    # (Also silences the dev cookie_secret warning in the child process.)
    env["BUDGET_ENV"] = "dev"
    # Well-known dev value used only by the e2e subprocess.
    env["BUDGET_COOKIE_SECRET"] = "e2e-dev-cookie-secret-not-a-real-secret"  # noqa: S105  # pragma: allowlist secret

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
def page(_browser: Browser, live_server: tuple[str, Path]) -> Iterator[Page]:
    """A Playwright ``Page`` with the CSRF token wired into ``page.request``.

    T-D08 — the CSRF middleware (ADR-0033 §4) rejects mutating requests
    that lack ``X-CSRF-Token``. E2E seeding uses ``page.request.post``
    which is an ``APIRequestContext`` call — it shares the browser
    context's cookie jar, so a priming GET stores the dev ``csrf`` cookie
    in the real jar (ADR-0065). Only the header is injected; the cookie
    travels through the browser exactly as it does for a user, so a
    cookie the browser refuses to store fails the suite instead of being
    papered over. HTMX requests get the header from the ``<meta>`` tag.
    """
    base_url, _db_path = live_server
    context = _browser.new_context()
    # Prime the cookie via the shared APIRequestContext.
    context.request.get(f"{base_url}/healthz")
    token = next(
        (c["value"] for c in context.cookies() if c["name"] == CSRF_DEV_COOKIE_NAME),
        "",
    )
    assert token, "browser did not store the CSRF cookie (ADR-0065)"
    # T-D02b — sign in through the real password form so the dev
    # ``session`` cookie lands in the browser jar (ADR-0070 §1).
    login = context.request.post(
        f"{base_url}/auth/login",
        form={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD,
            "next": "/",
            CSRF_FORM_FIELD: token,
        },
        max_redirects=0,
    )
    assert login.status == 303, f"e2e login failed: {login.status}"
    assert any(c["name"] == SESSION_DEV_COOKIE_NAME for c in context.cookies()), (
        "browser did not store the session cookie (ADR-0070)"
    )
    context.set_extra_http_headers({CSRF_HEADER_NAME: token})
    page = context.new_page()
    try:
        yield page
    finally:
        context.close()
