"""``--target={app,mockup}`` for the e2e harness (T-UT09, ADR-0106 section 5).

Load with ``pytest_plugins = ["tests.e2e.mockup_target"]`` in
``tests/e2e/conftest.py`` (or ``-p tests.e2e.mockup_target``). With
``--target=mockup`` a session fixture serves the handoff
(``docs/design/rising-dough-frontend/``, ``stand-in.js`` included) over
127.0.0.1 and ``journey`` navigates app routes to handoff pages through
``tests/ui_map/mockup_routes.py``.
"""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.ui_map.mockup_routes import HANDOFF_ROOT, handoff_page
from tests.ui_map.target import TARGETS, Target, surface


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--target",
        action="store",
        default="app",
        choices=TARGETS,
        help="e2e target: the live app (default) or the static design handoff",
    )


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        return


@dataclass(frozen=True)
class Journey:
    """Page plus target-aware navigation and UI-map lookup."""

    page: Any
    target: Target
    base_url: str

    def goto(self, route: str) -> None:
        """Open an app route (mockup: its mapped handoff page)."""
        path = f"/{handoff_page(route)}" if self.target == "mockup" else route
        self.page.goto(f"{self.base_url}{path}")

    def ui(self, name: str) -> ModuleType:
        return surface(name, self.target)


@pytest.fixture(scope="session")
def target(request: pytest.FixtureRequest) -> Target:
    value: Target = request.config.getoption("--target", default="app")
    return value


@pytest.fixture(scope="session")
def mockup_base_url(target: Target) -> Iterator[str]:
    """Serve the handoff over 127.0.0.1 (only started for ``--target=mockup``)."""
    if target != "mockup":
        yield ""
        return
    handler = functools.partial(_QuietHandler, directory=str(Path(HANDOFF_ROOT)))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def journey(request: pytest.FixtureRequest, target: Target) -> Iterator[Journey]:
    """A ``Journey`` on the selected target (logged-in app page, or mockup page)."""
    if target == "app":
        page = request.getfixturevalue("page")
        base_url, _db = request.getfixturevalue("live_server")
        yield Journey(page, target, base_url)
        return
    base_url = request.getfixturevalue("mockup_base_url")
    browser = request.getfixturevalue("_browser")
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    try:
        yield Journey(page, target, base_url)
    finally:
        context.close()


ResolveSurface = Callable[[str], ModuleType]
