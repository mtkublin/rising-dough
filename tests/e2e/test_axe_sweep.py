"""axe-core accessibility sweep over every crawled page route (T-Q300, ADR-0027 amendment
2026-11-23).

Advisory, opt-in: runs only when ``A11Y_SWEEP=1`` (set by ``.github/workflows/a11y-perf.yml``), so
the required ``tests/e2e`` job skips it and is unaffected. Reuses the crawl route list
(``test_crawl.PAGES`` / ``VIEWS``), the seeded scratch DB and the logged-in ``page`` fixture. axe-
core is vendored (``tests/e2e/vendor/axe.min.js``, pinned, no CDN). The app's CSP forbids injected
inline scripts, so the source is run through ``page.evaluate`` (CDP, not subject to page CSP).

Fails on serious and critical violations (colour contrast included) at 1440 and prints ``route |
rule | impact | nodes`` for each. Moderate and minor are reported but do not fail.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page

from tests.e2e.crawl.engine import DESKTOP, settle
from tests.e2e.crawl.seed import seed_world
from tests.e2e.redirect_routes import probe_routes
from tests.e2e.test_crawl import PAGES, VIEWS

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        os.environ.get("A11Y_SWEEP") != "1",
        reason="advisory axe sweep: set A11Y_SWEEP=1 (a11y-perf.yml)",
    ),
]

AXE_PATH = Path(__file__).parent / "vendor" / "axe.min.js"
FAIL_IMPACTS = ("serious", "critical")
REPORT_ENV = "A11Y_REPORT"

_RUN_JS = """async () => {
  const r = await axe.run(document, {resultTypes: ['violations']});
  return r.violations.map(v => ({
    id: v.id, impact: v.impact, help: v.help,
    nodes: v.nodes.length, targets: v.nodes.slice(0, 3).map(n => n.target.join(' '))
  }));
}"""


def _scan(page: Page, axe_source: str, url: str) -> list[dict[str, Any]]:
    page.goto(url)
    settle(page)
    page.evaluate(axe_source)
    violations: list[dict[str, Any]] = page.evaluate(_RUN_JS)
    return violations


def test_axe_sweep_serious_and_critical(page: Page, live_server: tuple[str, Path]) -> None:
    base_url, db_path = live_server
    seed_world(page.request, base_url, db_path)
    axe_source = AXE_PATH.read_text(encoding="utf-8")
    page.set_viewport_size(DESKTOP)  # type: ignore[arg-type]
    all_routes = (*PAGES, *VIEWS)
    routes, redirected = probe_routes(page.request, base_url, all_routes)
    print(
        f"axe scans {len(routes)} of {len(all_routes)} routes; "
        f"redirect-only, excluded by name: {redirected}"
    )
    report: dict[str, list[dict[str, Any]]] = {}
    failing: list[str] = []
    for route in routes:
        found = _scan(page, axe_source, base_url + route)
        report[route] = found
        for v in found:
            line = f"{route} | {v['id']} | {v['impact']} | {v['nodes']} node(s) | {v['targets'][0]}"
            print(line)
            if v["impact"] in FAIL_IMPACTS:
                failing.append(line)
    print(f"axe scanned {len(routes)} routes at {DESKTOP['width']}px")
    out = os.environ.get(REPORT_ENV)
    if out:
        Path(out).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    assert not failing, (
        f"{len(failing)} serious/critical axe violation(s) over {len(routes)} routes:\n"
        + "\n".join(failing)
    )
