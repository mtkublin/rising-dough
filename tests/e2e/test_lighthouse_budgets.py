"""Lighthouse / Core Web Vitals budgets over every crawled page route (T-Q300, ADR-0027 amendment
2026-11-23).

Advisory, opt-in: runs only when ``PERF_LHCI=1`` (set by ``.github/workflows/a11y-perf.yml``); the
required ``tests/e2e`` job skips it. Budgets live in ONE file, ``tests/perf/lighthouserc.json``.

Login: LHCI's puppeteer login needs a second browser stack. Instead this test reuses the e2e
``live_server`` + logged-in ``page`` fixtures (seeded scratch DB), reads the session cookie from
the browser context and hands it to Lighthouse as an ``extraHeaders`` Cookie. Same route list as
the crawl (``PAGES`` / ``VIEWS``, no second inventory). Chromium is the Playwright container's
own. ``@lhci/cli`` is run through ``npx`` at an exact pinned version (needs Node on PATH).
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from playwright.sync_api import Page, Playwright

from budget_planner.web.auth_cookies import SESSION_DEV_COOKIE_NAME
from tests.e2e.crawl.seed import seed_world
from tests.e2e.redirect_routes import probe_routes
from tests.e2e.test_crawl import PAGES, VIEWS

pytestmark = [pytest.mark.e2e]
_needs_lhci = pytest.mark.skipif(
    os.environ.get("PERF_LHCI") != "1",
    reason="advisory Lighthouse budgets: set PERF_LHCI=1 (a11y-perf.yml)",
)

LHCI_VERSION = "0.15.1"
CONFIG = Path(__file__).resolve().parents[1] / "perf" / "lighthouserc.json"
CADDYFILE = Path(__file__).resolve().parents[1] / "perf" / "Caddyfile"
CADDY_BIN_ENV = "PERF_CADDY_BIN"
LHCI_TIMEOUT_S = 1500
CADDY_READY_TIMEOUT_S = 15.0
CADDY_POLL_S = 0.1
LOCALHOST = "127.0.0.1"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind((LOCALHOST, 0))
        port: int = sock.getsockname()[1]
    return port


def _wait_until_listening(port: int) -> None:
    deadline = time.monotonic() + CADDY_READY_TIMEOUT_S
    while time.monotonic() < deadline:
        with socket.socket() as sock:
            if sock.connect_ex((LOCALHOST, port)) == 0:
                return
        time.sleep(CADDY_POLL_S)
    raise RuntimeError(f"caddy did not listen on {port} within {CADDY_READY_TIMEOUT_S}s")


@contextmanager
def _caddy_front(upstream_url: str) -> Iterator[str]:
    """Front the app with Caddy and the prod ``encode zstd gzip`` (ADR-0027 amendment 2026-11-24).

    The budgets are transfer sizes users receive, and in prod Caddy compresses; the app does not.
    ``PERF_CADDY_BIN`` is the caddy binary from prod's pinned image (a11y-perf.yml). Without
    it the app is measured bare, which reports raw sizes (local runs only).
    """
    binary = os.environ.get(CADDY_BIN_ENV)
    if not binary:
        yield upstream_url
        return
    port = _free_port()
    env = {
        **os.environ,
        "PERF_LISTEN": f"{LOCALHOST}:{port}",
        "PERF_UPSTREAM": upstream_url.removeprefix("http://"),
    }
    proc = subprocess.Popen(  # noqa: S603  # fixed argv, binary path from the workflow
        [binary, "run", "--config", str(CADDYFILE), "--adapter", "caddyfile"],
        env=env,
    )
    try:
        _wait_until_listening(port)
        yield f"http://{LOCALHOST}:{port}"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def _lhci(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603  # fixed argv, pinned package, no user input
        ["npx", "--yes", f"@lhci/cli@{LHCI_VERSION}", *args],  # noqa: S607  # npx from PATH (setup-node)
        env=env,
        capture_output=True,
        text=True,
        timeout=LHCI_TIMEOUT_S,
        check=False,
    )


def _sandbox_free_chrome(real: str, directory: Path) -> str:
    """Wrapper: LHCI launches Chrome itself; root in the container needs --no-sandbox."""
    wrapper = directory / "chrome-no-sandbox.sh"
    wrapper.write_text(f'#!/bin/sh\nexec "{real}" --no-sandbox --disable-dev-shm-usage "$@"\n')
    wrapper.chmod(0o755)
    return str(wrapper)


@_needs_lhci
def test_lighthouse_budgets(
    page: Page, live_server: tuple[str, Path], _playwright: Playwright, tmp_path: Path
) -> None:
    base_url, db_path = live_server
    seed_world(page.request, base_url, db_path)
    cookie = next(
        c["value"] for c in page.context.cookies() if c["name"] == SESSION_DEV_COOKIE_NAME
    )
    headers = json.dumps({"Cookie": f"{SESSION_DEV_COOKIE_NAME}={cookie}"})
    chrome = _sandbox_free_chrome(_playwright.chromium.executable_path, tmp_path)
    env = {**os.environ, "CHROME_PATH": chrome}
    routes = (*PAGES, *VIEWS)
    measured, redirected = probe_routes(page.request, base_url, routes)
    print(
        f"lighthouse measures {len(measured)} of {len(routes)} routes; "
        f"redirect-only, excluded by name: {redirected}"
    )
    with _caddy_front(base_url) as front_url:
        print(f"lighthouse target: {front_url} (app: {base_url})")
        urls = [f"{front_url}{route}" for route in measured]
        collect_args = [
            "collect",
            f"--config={CONFIG}",
            f"--collect.settings.extraHeaders={headers}",
            *[f"--collect.url={u}" for u in urls],
        ]
        collected = _lhci(collect_args, env)
    print(collected.stdout, collected.stderr)
    assert collected.returncode == 0, "lhci collect failed (not a budget result)"
    asserted = _lhci(["assert", f"--config={CONFIG}"], env)
    print(asserted.stdout, asserted.stderr)
    assert asserted.returncode == 0, (
        f"Lighthouse budgets exceeded over {len(urls)} of {len(routes)} routes "
        f"(redirect-only excluded: {redirected}):\n{asserted.stdout}{asserted.stderr}"
    )
