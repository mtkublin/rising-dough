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
import subprocess
from pathlib import Path

import pytest
from playwright.sync_api import Page, Playwright

from budget_planner.web.auth_cookies import SESSION_DEV_COOKIE_NAME
from tests.e2e.crawl.seed import seed_world
from tests.e2e.test_crawl import PAGES, VIEWS

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.environ.get("PERF_LHCI") != "1",
        reason="advisory Lighthouse budgets: set PERF_LHCI=1 (a11y-perf.yml)",
    ),
]

LHCI_VERSION = "0.15.1"
CONFIG = Path(__file__).resolve().parents[1] / "perf" / "lighthouserc.json"
LHCI_TIMEOUT_S = 1500


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
    urls = [f"{base_url}{route}" for route in (*PAGES, *VIEWS)]
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
        f"Lighthouse budgets exceeded over {len(urls)} routes:\n{asserted.stdout}{asserted.stderr}"
    )
