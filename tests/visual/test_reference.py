"""Handoff reference comparison (T-UT10, ADR-0106 amends ADR-0027 section 4).

Runs only with ``--reference=handoff`` (optionally ``--surface=<name>``):

* ``test_handoff_matches_itself``: re-renders each handoff page and requires 0
  diff against ``tests/visual/reference/``. Proves the references are stable.
* ``test_app_matches_handoff``: renders the app route that replaces a handoff
  page (frozen server, demo data at 2026-10-31) and compares within the
  per-surface tolerance. Skipped for surfaces not yet
  migrated by ADR-0107 (``MIGRATED_SURFACES``).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from playwright.sync_api import Browser

from tests.visual import handoff

pytestmark = pytest.mark.visual

# Surfaces whose templates have been migrated to the handoff markup. Empty
# until ADR-0107 work lands; add a surface here to turn on the app comparison.
MIGRATED_SURFACES: dict[str, str] = {}  # surface -> app route of its main page


def _selected(config: pytest.Config) -> list[str]:
    if config.getoption("--reference") != "handoff":
        return []
    surface = config.getoption("--surface")
    return [p for p in handoff.pages() if not surface or handoff.surface_of(p) == surface]


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "handoff_page" in metafunc.fixturenames:
        pages = _selected(metafunc.config)
        metafunc.parametrize(
            "handoff_page",
            pages or [pytest.param("-", marks=pytest.mark.skip("needs --reference=handoff"))],
        )


@pytest.mark.parametrize("theme", handoff.THEMES)
@pytest.mark.parametrize("viewport", list(handoff.VIEWPORTS))
def test_handoff_matches_itself(
    handoff_page: str, viewport: str, theme: str, browser: Browser
) -> None:
    expected = handoff.reference_path(handoff_page, viewport, theme)
    if not expected.exists():
        pytest.skip(
            f"reference not committed (size budget): {expected.name}; run `just visual-reference`"
        )
    with handoff.serve_handoff() as base, tempfile.TemporaryDirectory() as tmp:
        actual = Path(tmp) / "actual.png"
        handoff.shoot(browser, base, handoff_page, viewport=viewport, theme=theme, out=actual)
        ratio = handoff.diff_ratio(expected, actual)
    assert ratio <= handoff.SELF_TOLERANCE, (
        f"{handoff_page} {viewport} {theme}: {ratio:.4%} pixels differ"
    )


@pytest.mark.parametrize("theme", handoff.THEMES)
@pytest.mark.parametrize("viewport", list(handoff.VIEWPORTS))
def test_app_matches_handoff(
    handoff_page: str,
    viewport: str,
    theme: str,
    browser: Browser,
    request: pytest.FixtureRequest,
) -> None:
    surface = handoff.surface_of(handoff_page)
    route = MIGRATED_SURFACES.get(surface)
    if route is None or handoff_page != f"pages/{surface}.html":
        pytest.skip(f"surface {surface!r} not migrated to the handoff markup yet")
    live_server: str = request.getfixturevalue("live_server")
    cookies = request.getfixturevalue("session_cookies")
    width, height = handoff.VIEWPORTS[viewport]
    context = browser.new_context(
        viewport={"width": width, "height": height},
        reduced_motion="reduce",
        color_scheme=theme,  # type: ignore[arg-type]
        device_scale_factor=1,
    )
    try:
        context.add_cookies(cookies)
        context.clock.set_fixed_time(handoff.HANDOFF_FIXED_TIME)
        pg = context.new_page()
        pg.goto(f"{live_server}{route}", wait_until="networkidle", timeout=15000)
        pg.add_style_tag(content=handoff.FREEZE_CSS)
        pg.evaluate("document.fonts.ready.then(() => undefined)")
        with tempfile.TemporaryDirectory() as tmp:
            actual = Path(tmp) / "actual.png"
            pg.screenshot(path=str(actual), full_page=True)
            ratio = handoff.diff_ratio(
                handoff.reference_path(handoff_page, viewport, theme), actual
            )
    finally:
        context.close()
    assert ratio <= handoff.SURFACE_TOLERANCE[surface], (
        f"{route} {viewport} {theme}: {ratio:.2%} differ"
    )
