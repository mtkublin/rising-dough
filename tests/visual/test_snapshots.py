"""Full-page screenshot regression suite (ADR-0027 section 4).

Twelve snapshots: four top-level nav routes x three viewports (desktop,
tablet, mobile). First run with a missing baseline writes the baseline
and skips the test; `VISUAL_UPDATE=1` overwrites existing baselines.

Diff tolerance starts strict (byte-equal). The ADR allows <= 0.1 pixel
ratio via pixelmatch; wiring pixelmatch's Node CLI into pytest is a
Phase 10 follow-up - the strict byte compare already catches real
drift and keeps the first baseline suite trustworthy.
"""

from __future__ import annotations

import filecmp
import tempfile
from pathlib import Path
from typing import TypedDict

import pytest
from playwright.sync_api import Browser


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
]


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
        )
        context.add_cookies(session_cookies)  # type: ignore[arg-type]
        page = context.new_page()
        page.goto(f"{live_server}{route}", wait_until="networkidle", timeout=15000)
        page.wait_for_timeout(300)
        page.screenshot(path=str(shot), full_page=True)
        context.close()

        if update_baseline or not baseline.exists():
            baseline.write_bytes(shot.read_bytes())
            reason = "updated" if update_baseline else "created"
            pytest.skip(f"baseline {reason}: {baseline.name}")

        assert filecmp.cmp(baseline, shot, shallow=False), (
            f"visual diff for {route} @ {viewport['label']}: "
            f"new={shot}, baseline={baseline}. "
            "Inspect the new PNG; if the change is intentional, run "
            "`just test-visual-update` to refresh baselines."
        )
    finally:
        if shot.exists():
            shot.unlink()
