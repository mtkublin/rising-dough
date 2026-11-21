"""Unit-level proof that the crawler's checker catches breakage (T-UT07).

Serves a tiny fixture page from a fake origin (no app, no template change)
and runs the real ``activate`` against it.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from playwright.sync_api import Browser, Page, Route

from tests.e2e.crawl.engine import Recorder, activate, find_controls

pytestmark = pytest.mark.e2e

BASE = "http://crawl.test"
HTMX = (
    Path(__file__).resolve().parents[2] / "src/budget_planner/web/static/vendor/htmx-2.0.11.min.js"
)

PAGE = """<!doctype html><html><head><title>fixture</title>
<script src="/htmx.js"></script></head><body>
<div id="out">idle</div>
<button hx-get="/ok" hx-target="#out">Good swap</button>
<button hx-get="/missing" hx-target="#out">Broken target</button>
<button type="button">Inert</button>
</body></html>"""


def _serve(route: Route) -> None:
    path = route.request.url.removeprefix(BASE)
    if path == "/":
        route.fulfill(status=200, content_type="text/html", body=PAGE)
    elif path == "/htmx.js":
        route.fulfill(status=200, content_type="text/javascript", body=HTMX.read_text())
    elif path == "/ok":
        route.fulfill(status=200, content_type="text/html", body="swapped")
    else:
        route.fulfill(status=404, content_type="text/html", body="nope")


@pytest.fixture
def fixture_page(_browser: Browser) -> Iterator[Page]:
    context = _browser.new_context()
    context.route(f"{BASE}/**", _serve)
    page = context.new_page()
    yield page
    context.close()


def _run(page: Page, name: str) -> list[str]:
    recorder = Recorder(page, BASE)
    page.goto(BASE + "/")
    control = next(c for c in find_controls(page) if c.name == name)
    outcome = activate(
        page,
        recorder,
        base_url=BASE,
        route="/",
        control=control,
        via=None,
        on_destructive=lambda: None,
    )
    return outcome.problems


def test_healthy_hx_get_passes(fixture_page: Page) -> None:
    assert _run(fixture_page, "Good swap") == []


def test_broken_hx_get_target_is_reported(fixture_page: Page) -> None:
    problems = _run(fixture_page, "Broken target")
    assert any("HTTP 404" in p for p in problems), problems


def test_control_that_does_nothing_is_reported(fixture_page: Page) -> None:
    problems = _run(fixture_page, "Inert")
    assert any("did nothing" in p for p in problems), problems
