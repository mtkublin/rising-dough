"""Handoff reference comparison (T-UT10, ADR-0106 amends ADR-0027 section 4).

Runs only with ``--reference=handoff`` (optionally ``--surface=<name>``).
The references are never committed (T-UR00b, ADR-0147 section 1): the ``references``
fixture renders every selected page (overlay applied) at 1440/1024/375, light and
dark, into ``tests/visual/reference/`` in the same job and container first.

* ``test_handoff_matches_itself``: re-renders each handoff page and requires
  the raster noise floor against the fresh reference. Proves rendering is stable.
* ``test_app_matches_handoff``: renders the app route that replaces a handoff
  page (frozen server, handoff seed at 2026-10-31) and compares within the
  one strict tolerance (ratio and largest cluster, ADR-0147 section 2).
  Every surface is compared; red until it migrates.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from playwright.sync_api import Browser

from tests.visual import handoff

pytestmark = pytest.mark.visual

# Main app route of each handoff surface (the page its reference is compared with).
SURFACE_ROUTES: dict[str, str] = {
    "today": "/today",
    "accounts": "/accounts",
    "ledger": "/ledger",
    "plan": "/plan",
    "settings": "/settings",
    "auth": "/auth/login",
    "errors": "/settings/users/999999/edit",
    "overlays": "/today",
}
# Tab pages with their own app route (plan ?tab=, ledger ?view=, recently-deleted).
PAGE_ROUTES: dict[str, str] = {
    "pages/plan/year.html": "/plan?tab=year",
    "pages/plan/forecast.html": "/plan?tab=forecast",
    "pages/plan/analytics.html": "/plan?tab=analytics",
    "pages/ledger/planned.html": "/ledger?view=planned",
    "pages/ledger/recurring.html": "/ledger?view=recurring",
    "pages/ledger/recently-deleted.html": "/ledger/recently-deleted",
    "pages/errors/422.html": "/budget?month=zz",
}


@pytest.fixture(scope="session")
def references(request: pytest.FixtureRequest) -> int:
    """Render the handoff references once per session, before any comparison."""
    surface = request.config.getoption("--surface") or None
    return handoff.generate(surface)


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


def _keep_dir() -> Path:
    return Path(os.environ.get("VISUAL_KEEP_DIR", "visual-actual"))


def _record_self_cluster(page: str, viewport: str, theme: str, result: handoff.Comparison) -> None:
    """One line per self-comparison for calibrating ``MAX_DIFF_CLUSTER_PX`` (T-UR00b)."""
    keep = _keep_dir()
    keep.mkdir(parents=True, exist_ok=True)
    if result.cluster < 0:
        return
    with (keep / "self-clusters.txt").open("a") as fh:
        fh.write(f"{result.cluster} {page} {viewport} {theme}\n")


@pytest.mark.usefixtures("references")
@pytest.mark.parametrize("theme", handoff.THEMES)
@pytest.mark.parametrize("viewport", list(handoff.VIEWPORTS))
def test_handoff_matches_itself(
    handoff_page: str, viewport: str, theme: str, browser: Browser
) -> None:
    expected = handoff.reference_path(handoff_page, viewport, theme)
    assert expected.exists(), f"reference not rendered: {expected}"
    with handoff.serve_handoff() as base, tempfile.TemporaryDirectory() as tmp:
        actual = Path(tmp) / "actual.png"
        handoff.shoot(browser, base, handoff_page, viewport=viewport, theme=theme, out=actual)
        result = handoff.compare(expected, actual, ratio_limit=handoff.SELF_TOLERANCE)
    _record_self_cluster(handoff_page, viewport, theme, result)
    assert result.ratio <= handoff.SELF_TOLERANCE, (
        f"{handoff_page} {viewport} {theme}: {result.ratio:.4%} pixels differ, "
        f"largest cluster {result.cluster}px"
    )


@pytest.mark.usefixtures("references")
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
    route = PAGE_ROUTES.get(handoff_page, SURFACE_ROUTES[surface])
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
            result = handoff.compare(
                handoff.reference_path(handoff_page, viewport, theme),
                actual,
                ratio_limit=handoff.MAX_DIFF_PIXEL_RATIO,
                cluster_cap=handoff.MAX_DIFF_CLUSTER_PX,
            )
            ok = (
                result.ratio <= handoff.MAX_DIFF_PIXEL_RATIO
                and result.cluster <= handoff.MAX_DIFF_CLUSTER_PX
            )
            if not ok:
                stem = Path(handoff_page).with_suffix("").as_posix().replace("/", "_")
                handoff.write_diff_png(result, _keep_dir() / f"{stem}.{viewport}.{theme}.diff.png")
    finally:
        context.close()
    cluster = (
        "not computed (ratio over the limit)"
        if result.cluster < 0
        else f"> {handoff.MAX_DIFF_CLUSTER_PX}px"
        if result.cluster > handoff.MAX_DIFF_CLUSTER_PX
        else f"{result.cluster}px"
    )
    assert ok, (
        f"{route} {viewport} {theme}: {result.ratio:.4%} differ "
        f"(max {handoff.MAX_DIFF_PIXEL_RATIO:.2%}), largest cluster {cluster} "
        f"(max {handoff.MAX_DIFF_CLUSTER_PX}px) at {result.box}"
    )
