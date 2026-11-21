"""E2E smoke-test fixtures.

Boots a real uvicorn process on an ephemeral loopback port against a
per-test migrated+seeded SQLite file, yields a Playwright page, and
tears everything down. If the Playwright browser is not installed the
whole suite is skipped with a clear message instead of crashing.
"""

from __future__ import annotations

import os
import re
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
from tests.e2e.csp import TEST_NONCE, prod_csp
from tests.e2e.mockup_target import journey, mockup_base_url, target  # noqa: F401

# Loaded machines can take well over 15s to boot uvicorn. Override with
# E2E_SERVER_READY_TIMEOUT_S; a server that exits early fails at once anyway.
SERVER_READY_TIMEOUT_S = float(os.environ.get("E2E_SERVER_READY_TIMEOUT_S", "60"))

try:
    from playwright.sync_api import Browser, Page, Playwright, Route, sync_playwright
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


E2E_BROWSERS = ("chromium", "firefox", "webkit")

# T-UT11 (ADR-0106 §4): known per-browser failures on the old UI. Keys are
# ``(browser, test nodeid suffix)``; values are the xfail reason. Chromium is
# never listed here. Applied as ``xfail(strict=True)`` so a fix flips to XPASS
# and fails loudly, forcing the entry's removal.
_CDP_ONLY = "journey drives a CDP virtual WebAuthn authenticator (Chromium-only API)"
BROWSER_XFAILS: dict[tuple[str, str], str] = {
    (browser, f"test_passkey_journey.py::{name}"): _CDP_ONLY
    for browser in ("firefox", "webkit")
    for name in (
        "test_register_then_sign_in_with_passkey",
        "test_stale_session_adds_passkey_after_password_reauth",
        "test_stale_session_reauths_with_passkey",
    )
}


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--e2e-browser",
        action="store",
        default="chromium",
        choices=E2E_BROWSERS,
        help="Playwright browser engine for tests/e2e (default: chromium).",
    )


def _selected_browser(config: pytest.Config) -> str:
    return str(config.getoption("--e2e-browser"))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    browser = _selected_browser(config)
    if browser == "chromium":
        return
    for item in items:
        for (name, suffix), reason in BROWSER_XFAILS.items():
            if name == browser and item.nodeid.endswith(suffix):
                item.add_marker(pytest.mark.xfail(strict=True, reason=f"{browser}: {reason}"))


@pytest.fixture(scope="session")
def _browser(_playwright: Playwright, request: pytest.FixtureRequest) -> Iterator[Browser]:
    name = _selected_browser(request.config)
    try:
        browser = getattr(_playwright, name).launch()
    except Exception as exc:
        pytest.skip(f"{name} browser is not installed: {exc}")
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


def _wait_until_ready(
    url: str,
    deadline_s: float = SERVER_READY_TIMEOUT_S,
    proc: subprocess.Popen[bytes] | None = None,
) -> None:
    start = time.monotonic()
    while time.monotonic() - start < deadline_s:
        if proc is not None and proc.poll() is not None:
            raise RuntimeError(
                f"uvicorn exited with code {proc.returncode} before becoming ready at {url}"
            )
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
        _wait_until_ready(f"{base_url}/health", proc=proc)
        yield base_url, db_path
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


_CSP_CONSOLE = re.compile(r"Content Security Policy")

_CSP_LISTENER_JS = """
document.addEventListener('securitypolicyviolation', (e) => {
  window.__reportCspViolation(
    `event: ${e.violatedDirective} blocked ${e.blockedURI || 'inline'}` +
    ` at ${e.sourceFile}:${e.lineNumber}`
  );
});
"""


# T-D150: htmx raises ``htmx:targetError`` (and sends no request) when an
# ``hx-target`` selector matches nothing. The event bubbles from the element,
# so one document listener sees every one. ``sendError`` / ``responseError``
# are deliberately not recorded: 422/429 are swapped on purpose
# (``static/js/app-init.js``) and navigation aborts would add noise.
_HTMX_TARGET_ERROR_JS = """
document.addEventListener('htmx:targetError', (e) => {
  const el = e.detail && e.detail.elt ? e.detail.elt : e.target;
  const d = e.detail || {};
  const who = el && el.tagName
    ? `${el.tagName.toLowerCase()}#${el.id || ''}.${String(el.className || '').trim()}`
    : 'unknown element';
  window.__reportHtmxTargetError(
    `htmx:targetError: hx-target ${JSON.stringify(d.target || null)} not found for ${who}` +
    ` at ${location.pathname}`
  );
});
"""


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
            "next": "/today",
            CSRF_FORM_FIELD: token,
        },
        max_redirects=0,
    )
    assert login.status == 303, f"e2e login failed: {login.status}"
    assert any(c["name"] == SESSION_DEV_COOKIE_NAME for c in context.cookies()), (
        "browser did not store the session cookie (ADR-0070)"
    )
    # ADR-0113 / T-D140c: run under the real prod CSP. Dev has no Caddy, so
    # send the nonce header and add the CSP to HTML responses ourselves.
    context.set_extra_http_headers({CSRF_HEADER_NAME: token, "X-CSP-Nonce": TEST_NONCE})
    csp = prod_csp()
    violations: list[str] = []

    def _add_csp(route: Route) -> None:
        response = route.fetch(max_redirects=0)
        headers = dict(response.headers)
        if "text/html" in headers.get("content-type", ""):
            headers["content-security-policy"] = csp
        route.fulfill(response=response, headers=headers)

    context.route(f"{base_url}/**", _add_csp)

    def _record(message: str) -> None:
        violations.append(message)

    context.expose_function("__reportCspViolation", _record)
    context.add_init_script(_CSP_LISTENER_JS)
    target_errors: list[str] = []

    def _record_target_error(message: str) -> None:
        target_errors.append(message)

    context.expose_function("__reportHtmxTargetError", _record_target_error)
    context.add_init_script(_HTMX_TARGET_ERROR_JS)
    page = context.new_page()
    page.on(
        "console",
        lambda m: (
            violations.append(f"console: {m.text}")
            if m.type == "error" and _CSP_CONSOLE.search(m.text)
            else None
        ),
    )
    try:
        yield page
        unique = sorted(set(violations))
        assert not unique, "CSP violations under the prod policy:\n" + "\n".join(unique)
        missing = sorted(set(target_errors))
        assert not missing, "htmx target errors (hx-target matches nothing):\n" + "\n".join(missing)
    finally:
        # Let in-flight HTMX requests finish before the routes are torn down.
        context.unroute_all(behavior="ignoreErrors")
        context.close()
