"""Full-page screenshot regression suite (ADR-0027 section 4, amendment 2026-11-22, T-Q251).

Eight routes x three viewports (375, 1024, 1440), light theme (the app has no
dark mode, requirements section 4). Data is a scratch copy of
``data/demo.sqlite`` served by the frozen-clock server; animations are frozen
and the browser clock is pinned; fonts are the repo's local woff2 files.

Baselines live in ``tests/visual/__snapshots__/`` and are generated only inside
the pinned Playwright container (``just visual-update`` or the
``update_baselines`` dispatch of ``visual.yml``), never on macOS. A screenshot
passes when at most ``MAX_DIFF_PIXEL_RATIO`` of its pixels differ. A missing
baseline fails when ``CI`` is set and skips with instructions otherwise.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Final, TypedDict

import pytest
from playwright.sync_api import Browser

from tests.visual.conftest import FROZEN_DATE
from tests.visual.handoff import diff_ratio

MAX_DIFF_PIXEL_RATIO: Final = 0.001
"""Perceptual tolerance: 0.1 percent of pixels may differ (raster noise floor)."""


class _Viewport(TypedDict):
    width: int
    height: int


VIEWPORTS: Final = {
    "1440": _Viewport(width=1440, height=900),
    "1024": _Viewport(width=1024, height=768),
    "375": _Viewport(width=375, height=812),
}
ROUTES: Final = {
    "ledger": "/ledger",
    "accounts": "/accounts",
    "budget": "/budget",
    "forecast": "/forecast",
    "recurring": "/recurring/new",
    "settings": "/settings",
    "login": "/login",
}
SIGNED_OUT: Final = frozenset({"login"})
FONT_HOSTS: Final = ("**://fonts.googleapis.com/**", "**://fonts.gstatic.com/**")

# Kill transitions/animations/carets so a screenshot never lands mid-motion.
FREEZE_CSS: Final = """
*, *::before, *::after {
  animation: none !important;
  transition: none !important;
  caret-color: transparent !important;
  scroll-behavior: auto !important;
}
"""
UPDATE_HINT: Final = (
    "Baselines are generated only in the pinned Playwright container: run "
    "`just visual-update` (needs docker) or dispatch the Visual workflow with update_baselines."
)


def _shoot(
    browser: Browser, url: str, viewport: _Viewport, cookies: list[dict[str, str]], out: Path
) -> None:
    context = browser.new_context(
        viewport=viewport, reduced_motion="reduce", color_scheme="light", device_scale_factor=1
    )
    try:
        if cookies:
            context.add_cookies(cookies)  # type: ignore[arg-type]  # Playwright Cookie TypedDict vs plain dict
        context.clock.set_fixed_time(f"{FROZEN_DATE}T10:00:00Z")
        page = context.new_page()
        for pattern in FONT_HOSTS:  # hermetic: only the repo's local fonts
            page.route(pattern, lambda route: route.abort())
        page.goto(url, wait_until="networkidle", timeout=15000)
        page.add_style_tag(content=FREEZE_CSS)
        page.evaluate("document.fonts.ready.then(() => undefined)")
        page.evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
        page.screenshot(path=str(out), full_page=True)
    finally:
        context.close()


@pytest.mark.visual
@pytest.mark.parametrize("viewport_name", VIEWPORTS)
@pytest.mark.parametrize("route_name", ROUTES)
def test_route_snapshot(
    *,
    route_name: str,
    viewport_name: str,
    live_server: str,
    session_cookies: list[dict[str, str]],
    browser: Browser,
    baselines_dir: Path,
    update_baseline: bool,
) -> None:
    baseline = baselines_dir / f"{route_name}.{viewport_name}.png"
    missing = not update_baseline and not baseline.exists()
    if missing and not os.environ.get("CI"):
        pytest.skip(f"missing baseline {baseline.name}. {UPDATE_HINT}")
    cookies = [] if route_name in SIGNED_OUT else session_cookies
    with tempfile.TemporaryDirectory() as tmp:
        shot = Path(tmp) / baseline.name
        _shoot(
            browser, f"{live_server}{ROUTES[route_name]}", VIEWPORTS[viewport_name], cookies, shot
        )
        if update_baseline or missing:
            # Bootstrap: in CI a missing baseline still writes the actual shot to the baseline path
            # (the workflow uploads it as the visual-baselines artifact on failure), then fails.
            baselines_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(shot, baseline)
            if update_baseline:
                return
            pytest.fail(
                f"missing baseline {baseline.name} (actual written for the artifact). {UPDATE_HINT}"
            )
        ratio = diff_ratio(baseline, shot)
        if ratio > MAX_DIFF_PIXEL_RATIO:
            keep = Path(os.environ.get("VISUAL_KEEP_DIR", "visual-actual"))
            keep.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(shot, keep / baseline.name)
        assert ratio <= MAX_DIFF_PIXEL_RATIO, (
            f"{route_name} @ {viewport_name}: {ratio:.4%} of pixels differ "
            f"(limit {MAX_DIFF_PIXEL_RATIO:.2%}); actual image kept as {baseline.name} in "
            "VISUAL_KEEP_DIR. If the change is intentional, refresh the baselines. " + UPDATE_HINT
        )
