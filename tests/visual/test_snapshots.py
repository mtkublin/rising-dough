"""Full-page screenshot regression suite (ADR-0027 section 4).

Fifteen snapshots: five top-level nav routes x three viewports (desktop,
tablet, mobile). First run with a missing baseline writes the baseline
and skips the test; `VISUAL_UPDATE=1` overwrites existing baselines.

Diff tolerance starts strict (byte-equal). The ADR allows <= 0.1 pixel
ratio via pixelmatch; wiring pixelmatch's Node CLI into pytest is a
Phase 10 follow-up - the strict byte compare already catches real
drift and keeps the first baseline suite trustworthy.
"""

from __future__ import annotations

import filecmp
import os
import shutil
import tempfile
from pathlib import Path
from typing import TypedDict

import pytest
from playwright.sync_api import Browser

from tests.visual.conftest import FROZEN_DATE


class _Viewport(TypedDict):
    label: str
    width: int
    height: int


VIEWPORTS = [
    pytest.param(_Viewport(label="desktop", width=1440, height=900), id="desktop"),
    pytest.param(_Viewport(label="tablet", width=1024, height=768), id="tablet"),
    pytest.param(_Viewport(label="mobile", width=375, height=812), id="mobile"),
]
ROUTES = [
    pytest.param("/today", id="today"),
    pytest.param("/ledger", id="ledger"),
    pytest.param("/accounts", id="accounts"),
    pytest.param("/budget", id="budget"),
    pytest.param("/plan", id="plan"),
]


FONT_HOSTS = ("**://fonts.googleapis.com/**", "**://fonts.gstatic.com/**")

# Kill transitions/animations/carets so a screenshot never lands mid-motion.
FREEZE_CSS = """
*, *::before, *::after {
  animation: none !important;
  transition: none !important;
  caret-color: transparent !important;
  scroll-behavior: auto !important;
}
"""


def _slug(route: str, viewport: _Viewport) -> str:
    path = route.replace("/", "_") or "root"
    return f"{viewport['label']}__{path}.png"


@pytest.mark.visual
@pytest.mark.parametrize("viewport", VIEWPORTS)
@pytest.mark.parametrize("route", ROUTES)
def test_route_snapshot(
    *,
    route: str,
    viewport: _Viewport,
    live_server: str,
    session_cookies: list[dict[str, str]],
    browser: Browser,
    baselines_dir: Path,
    update_baseline: bool,
) -> None:
    baseline = baselines_dir / _slug(route, viewport)
    baselines_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        shot = Path(tmp.name)
    try:
        context = browser.new_context(
            viewport={"width": viewport["width"], "height": viewport["height"]},
            reduced_motion="reduce",
            color_scheme="light",
            device_scale_factor=1,
        )
        context.add_cookies(session_cookies)  # type: ignore[arg-type]
        # Browser clock pinned to the same day as the server (T-VIS5).
        context.clock.set_fixed_time(f"{FROZEN_DATE}T10:00:00Z")
        page = context.new_page()
        if not os.environ.get("VISUAL_REAL_FONTS"):
            # Hermetic fonts: Google Fonts load nondeterministically (swap
            # timing, per-run glyph raster) and made every snapshot flaky.
            for pattern in FONT_HOSTS:
                page.route(pattern, lambda route: route.abort())
        page.goto(f"{live_server}{route}", wait_until="networkidle", timeout=15000)
        page.add_style_tag(content=FREEZE_CSS)
        page.evaluate("document.fonts.ready.then(() => undefined)")
        page.evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
        page.screenshot(path=str(shot), full_page=True)
        context.close()

        if update_baseline or not baseline.exists():
            baseline.write_bytes(shot.read_bytes())
            reason = "updated" if update_baseline else "created"
            pytest.skip(f"baseline {reason}: {baseline.name}")

        keep = os.environ.get("VISUAL_KEEP_DIR")
        if keep:
            Path(keep).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(shot, Path(keep) / baseline.name)

        assert filecmp.cmp(baseline, shot, shallow=False), (
            f"visual diff for {route} @ {viewport['label']}: "
            f"new={shot}, baseline={baseline}. "
            "Inspect the new PNG; if the change is intentional, run "
            "`just test-visual-update` to refresh baselines."
        )
    finally:
        if shot.exists():
            shot.unlink()
