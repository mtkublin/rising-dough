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

import contextlib
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.web.auth_cookies import SESSION_DEV_COOKIE_NAME
from tests.visual import handoff
from tests.visual.handoff_openers import OPENERS, opener_url

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
# Overlay pages whose dialog the app opens from a plain GET: the new-entry shell page
# (`/add?dialog=1&when=<tab>`) renders the page with the dialog open (T-UR07b).
OVERLAY_DIALOGS: dict[str, str] = {
    "pages/overlays/new-entry--happened.html": "/add?dialog=1&when=happened",
    "pages/overlays/new-entry--planned.html": "/add?dialog=1&when=planned",
    "pages/overlays/new-entry--repeats-fixed.html": "/add?dialog=1&when=repeats",
}
# Overlay pages whose dialog the app opens from a dialog route (id-bound ones resolved from
# the seed): `handoff_openers.OPENERS`; the test loads /today and fetches it into #modal-root.
# Overlay pages with no way to open their dialog yet (row menus, palette and pickers, POST
# error states, settings/users dialogs, formula editor states): compared against plain /today.
UNMAPPED_OVERLAYS: frozenset[str] = frozenset(
    {
        "add-user--error",
        "add-user",
        "category-picker--no-match",
        "category-picker",
        "command-palette--filtered",
        "command-palette--no-match",
        "command-palette",
        "delete-account--blocked-planned",
        "delete-account",
        "delete-user",
        "edit-recurring--empty",
        "edit-recurring--incomplete",
        "edit-recurring--picking",
        "edit-transaction--error",
        "edit-user",
        "invite-user--error",
        "invite-user",
        "new-account--error",
        "new-account--filled",
        "new-category--error",
        "new-category--filled",
        "new-entry--error",
        "new-entry--over-limit",
        "new-entry--phone-sheet",
        "new-entry--repeats-formula",
        "one-time-password",
        "override--remove",
        "override--year-cell",
        "period-picker--year",
        "period-picker",
        "reset-password",
        "revoke-invite",
        "row-menu--account",
        "row-menu--budget",
        "row-menu--planned",
        "row-menu--recurring",
        "row-menu--transaction",
        "row-menu--upcoming",
        "shortcuts",
    }
)
OPENER_PAGES: frozenset[str] = frozenset(f"pages/overlays/{n}.html" for n in OPENERS)
# Pages that need the base seed plus named modifiers (handoff_seed.MODIFIER_NAMES).
PAGE_MODIFIERS: dict[str, tuple[str, ...]] = {
    "pages/ledger/recurring.html": ("recurring-board",),
}


def route_for(page: str) -> str:
    """App route compared with a handoff page (overlay dialogs, tab pages, surface default)."""
    return (
        OVERLAY_DIALOGS.get(page)
        or PAGE_ROUTES.get(page)
        or SURFACE_ROUTES[handoff.surface_of(page)]
    )


def modifiers_for(page: str) -> tuple[str, ...]:
    return PAGE_MODIFIERS.get(page, ())


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
    assert not result.size_mismatch and result.ratio <= handoff.SELF_TOLERANCE, (
        f"{handoff_page} {viewport} {theme}: "
        f"sizes {result.expected_size} vs {result.actual_size}, "
        f"{result.ratio:.4%} pixels differ, "
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
    route = route_for(handoff_page)
    modifiers = modifiers_for(handoff_page)
    opener: str | None = None
    with contextlib.ExitStack() as stack:
        if modifiers:
            server, token = stack.enter_context(
                request.getfixturevalue("handoff_server")(modifiers)
            )
            cookies = [{"name": SESSION_DEV_COOKIE_NAME, "value": token, "url": server}]
        else:
            server = request.getfixturevalue("live_server")
            cookies = request.getfixturevalue("session_cookies")
            opener = _opener_for(handoff_page, request.getfixturevalue("scratch_db")[0])
        _compare_app(
            handoff_page,
            route,
            viewport=viewport,
            theme=theme,
            browser=browser,
            live_server=server,
            cookies=cookies,
            opener=opener,
        )


def _opener_for(handoff_page: str, db_path: Path) -> str | None:
    """Dialog route of an overlay page, ids resolved from the seeded scratch DB (read-only)."""
    if handoff_page not in OPENER_PAGES:
        return None
    conn = get_connection(Settings(_env_file=None, database_url=f"sqlite:///{db_path.as_posix()}"))
    try:
        return opener_url(handoff_page, conn)
    finally:
        conn.close()


def _compare_app(
    handoff_page: str,
    route: str,
    *,
    viewport: str,
    theme: str,
    browser: Browser,
    live_server: str,
    cookies: list[Any],
    opener: str | None = None,
) -> None:
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
        if opener:
            pg.evaluate(
                "url => window.htmx.ajax('GET', url, {target: '#modal-root', swap: 'innerHTML'})",
                opener,
            )
            pg.wait_for_selector("#modal-root dialog[open]", timeout=15000)
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
            ok = handoff.passes(
                result,
                ratio_limit=handoff.MAX_DIFF_PIXEL_RATIO,
                cluster_cap=handoff.MAX_DIFF_CLUSTER_PX,
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
    sizes = (
        f"SIZE MISMATCH handoff {result.expected_size[0]}x{result.expected_size[1]}, "
        f"app {result.actual_size[0]}x{result.actual_size[1]}; "
        if result.size_mismatch
        else ""
    )
    assert ok, (
        f"{route} {viewport} {theme}: {sizes}{result.ratio:.4%} differ "
        f"(max {handoff.MAX_DIFF_PIXEL_RATIO:.2%}), largest cluster {cluster} "
        f"(max {handoff.MAX_DIFF_CLUSTER_PX}px) at {result.box}"
    )
