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
import re
import tempfile
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Browser

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.web.auth_cookies import SESSION_DEV_COOKIE_NAME
from tests.visual import handoff
from tests.visual.conftest import serve_db
from tests.visual.handoff_clicks import click_recipe
from tests.visual.handoff_forms import DIALOG_SUBMITS, submit_dialog
from tests.visual.handoff_openers import OPENERS, opener_url
from tests.visual.handoff_recurring import STATE_PAGES, state_opener_url, state_recipe
from tests.visual.handoff_seed import build_seed

pytestmark = pytest.mark.visual

# Main app route of each handoff surface: the page its reference is compared with when the page
# has no entry of its own below. `auth` and `errors` are only the fallback of the pages listed in
# UNMAPPED_PAGES (the mapping test fails a page that is neither mapped nor listed there).
SURFACE_ROUTES: dict[str, str] = {
    "today": "/today",
    "accounts": "/accounts",
    "ledger": "/ledger",
    "plan": "/plan",
    "settings": "/settings",
    "auth": "/auth/login",
    "errors": "/settings/users/999999/edit",
    # No "overlays" entry: an overlay page renders over its own base page (`base_page_of`).
}
# The invite link of the base seed (handoff_seed SeedData.invite_link).
_INVITE = "/invite/handoff-invite-accountant"
LEDGER_BOARD = "/ledger?date_from=2026-10-07&date_to=2026-10-31&page_size=11"
_NO_MATCHES = LEDGER_BOARD + "&q=pizza"
# Pages with their own app route (plan ?tab=, ledger ?view=, settings tabs, auth, errors).
PAGE_ROUTES: dict[str, str] = {
    "pages/plan/year.html": "/plan?tab=year",
    "pages/plan/forecast.html": "/plan?tab=forecast",
    "pages/plan/analytics.html": "/plan?tab=analytics",
    "pages/ledger/actual.html": LEDGER_BOARD,
    "pages/ledger/actual--long.html": LEDGER_BOARD,
    "pages/ledger/planned.html": "/ledger?view=planned",
    "pages/ledger/planned--empty.html": "/ledger?view=planned",
    "pages/ledger/recurring.html": "/ledger?view=recurring",
    "pages/ledger/recurring--empty.html": "/ledger?view=recurring",
    "pages/ledger/recently-deleted.html": "/ledger/recently-deleted",
    # The handoff board (4 day groups, 11 rows) with its "pizza" search (category chip needs an id).
    "pages/ledger/actual--no-matches.html": _NO_MATCHES,
    "pages/errors/422.html": "/budget?month=zz",
    "pages/settings/preferences.html": "/settings?tab=prefs",
    "pages/settings/currency-fx.html": "/settings?tab=fx",
    "pages/settings/security.html": "/settings/security",
    "pages/settings/security--error.html": "/settings/security",
    "pages/settings/users.html": "/settings/users",
    "pages/auth/login.html": "/auth/login",
    "pages/auth/login--error.html": "/auth/login",
    "pages/auth/reauth.html": "/auth/reauth",
    "pages/auth/reauth--error.html": "/auth/reauth",
    "pages/auth/invite.html": _INVITE,
    "pages/auth/invite--expired.html": _INVITE,
    "pages/auth/invite--used.html": _INVITE,
    "pages/auth/invite--invalid.html": "/invite/not-a-real-invite-token",
}
# Auth pages a signed-out visitor sees: rendered without the session cookie (a signed-in user is
# redirected away from /auth/login). Reauth needs the session and is not listed.
ANONYMOUS_PAGES: frozenset[str] = frozenset(
    {
        "pages/auth/login.html",
        "pages/auth/login--error.html",
        "pages/auth/invite.html",
        "pages/auth/invite--expired.html",
        "pages/auth/invite--used.html",
        "pages/auth/invite--invalid.html",
        "pages/auth/register.html",
        "pages/auth/register--error.html",
    }
)
# Error states reached by a failing form POST: the harness fills the fields (CSS selector, value)
# and presses Enter in the last one (the browser sends the CSRF token with the form), so the app
# answers with the error page the handoff shows.
FORM_SUBMITS: dict[str, tuple[tuple[str, str], ...]] = {
    "pages/auth/login--error.html": (
        ("input[name=email]", "owner@example.test"),
        ("input[type=password]", "wrong-password-1"),
    ),
    "pages/auth/reauth--error.html": (("input[type=password]", "wrong-password-1"),),
}
_SETUP_ONLY_EMPTY = "first-run setup (/setup) is open only with no users; the seed has users"
_NEEDS_ROTATION_USER = "needs a signed-in user with must_change_password; no seed modifier"
# Handoff pages (not overlays) the harness cannot reach yet: page -> why. Like UNMAPPED_OVERLAYS
# they are still compared with their surface's fallback route (red); the unmapped-state item maps
# them and this dict only shrinks.
UNMAPPED_PAGES: dict[str, str] = {
    "pages/settings/security--error.html": (
        "POST /settings/password re-renders the forced-rotation page, not the Security tab"
        " with the inline error"
    ),
    "pages/auth/register.html": _SETUP_ONLY_EMPTY,
    "pages/auth/register--error.html": _SETUP_ONLY_EMPTY,
    "pages/auth/force-password.html": _NEEDS_ROTATION_USER,
    "pages/auth/force-password--error.html": _NEEDS_ROTATION_USER,
    "pages/errors/409.html": "needs a version-conflict response; no GET renders the 409 card",
    "pages/errors/500.html": "needs a server error; no GET renders the 500 card",
    "pages/errors/offline.html": "the offline card is a client-side (service worker) state",
    "pages/today--afford-invalid.html": "needs the afford check submitted with invalid input",
    "pages/today--afford-over.html": "needs the afford check submitted over the limit",
    "pages/today--flash.html": "needs the saved-toast flash state after a write",
    "pages/today--loading.html": "needs the hero's loading (skeleton) state",
}
# Overlay pages whose dialog the app opens from a plain GET (the new-entry dialog,
# `/add?when=<tab>`, T-UR07b). Like every opener it is fetched into #modal-root over the
# overlay's base page (Today), never loaded as a blank shell.
OVERLAY_DIALOGS: dict[str, str] = {
    "pages/overlays/new-entry--happened.html": "/add?when=happened",
    "pages/overlays/new-entry--planned.html": "/add?when=planned",
    "pages/overlays/new-entry--repeats-fixed.html": "/add?when=repeats",
}
# Overlay pages whose dialog the app opens from a dialog route (id-bound ones resolved from
# the seed): `handoff_openers.OPENERS`; the test loads the overlay's base page and fetches it
# into #modal-root.
# Overlay pages with no way to open their state yet (the year-cell inline editor, POST
# error states); click and key states are
# `handoff_clicks.CLICK_RECIPES`: compared against their plain
# base page.
UNMAPPED_OVERLAYS: frozenset[str] = frozenset(
    {
        "delete-account--blocked-planned",
        "delete-account",
        "new-account--error",
        "new-account--filled",
        "new-category--error",
        "new-category--filled",
        "new-entry--error",
        "new-entry--over-limit",
        "new-entry--phone-sheet",
        "new-entry--repeats-formula",
        "override--year-cell",
    }
)
OPENER_PAGES: frozenset[str] = frozenset(f"pages/overlays/{n}.html" for n in OPENERS)
# Pages that need the base seed plus named modifiers (handoff_seed.MODIFIER_NAMES).
PAGE_MODIFIERS: dict[str, tuple[str, ...]] = {
    "pages/ledger/recurring.html": ("recurring-board",),
    "pages/today--empty.html": ("empty",),
    "pages/accounts--empty.html": ("empty-accounts",),
    "pages/ledger/actual--empty.html": ("empty-ledger",),
    "pages/ledger/planned--empty.html": ("empty-planned",),
    "pages/ledger/recurring--empty.html": ("empty-recurring",),
    "pages/ledger/actual--long.html": ("long",),
    "pages/ledger/actual--no-matches.html": ("no-matches",),
    "pages/auth/invite--expired.html": ("invite-expired",),
    "pages/auth/invite--used.html": ("invite-used",),
    # Fresh DB per run: the wrong-password POST must not eat a shared rate limit.
    "pages/auth/login--error.html": ("form-error",),
    "pages/auth/reauth--error.html": ("form-error",),
}


_ANCHOR = re.compile(r"<a\b[^>]*>")
_HREF = re.compile(r'href="([^"]*)"')
# An overlay file with no current nav item shows the Today board.
_DEFAULT_BASE = "pages/today.html"


def base_page_of(page: str) -> str:
    """Handoff page behind an overlay: the surface board the overlay file shows around its dialog.

    Derived from the file: the tab link with ``aria-current="page"`` (a tab that is not another
    overlay: ledger planned / recurring, settings categories, plan budget) wins over the main-nav
    link (ledger actual, accounts, today). Non-overlay pages are their own base.
    """
    if handoff.surface_of(page) != "overlays":
        return page
    tab = nav = None
    for tag in _ANCHOR.findall((handoff.HANDOFF_ROOT / page).read_text(encoding="utf-8")):
        href = _HREF.search(tag)
        if 'aria-current="page"' not in tag or not href or "pages/" not in href.group(1):
            continue
        target = "pages/" + href.group(1).split("pages/", 1)[1].split("?", 1)[0]
        if handoff.surface_of(target) == "overlays":
            continue
        if "rd-tabs__tab" in tag:
            tab = tab or target
        elif "rd-mainnav__link" in tag or "rd-topbar__link" in tag:
            nav = nav or target
    return tab or nav or _DEFAULT_BASE


def route_for(page: str) -> str:
    """App route compared with a handoff page (tab pages; overlays: their base page's route)."""
    base = base_page_of(page)
    return PAGE_ROUTES.get(base) or SURFACE_ROUTES[handoff.surface_of(base)]


def is_anonymous(page: str) -> bool:
    """Whether the page renders for a signed-out visitor (no session cookie)."""
    return page in ANONYMOUS_PAGES


def modifiers_for(page: str) -> tuple[str, ...]:
    """Seed modifiers of a page; an overlay takes its base page's (recurring-board)."""
    return PAGE_MODIFIERS.get(base_page_of(page), ())


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
    with contextlib.ExitStack() as stack:
        if modifiers or handoff_page in DIALOG_SUBMITS or handoff_page in STATE_PAGES:
            # Own seeded DB: the opener's ids are resolved from the DB being served (and a
            # submitted dialog, e.g. a password reset, must not change the shared one).
            tmp_path_factory = request.getfixturevalue("tmp_path_factory")
            db_path = tmp_path_factory.mktemp("handoff-state") / "handoff.sqlite"
            token = build_seed(db_path, modifiers=modifiers).session_token
            server = stack.enter_context(serve_db(db_path))
            cookies = [{"name": SESSION_DEV_COOKIE_NAME, "value": token, "url": server}]
        else:
            server = request.getfixturevalue("live_server")
            cookies = request.getfixturevalue("session_cookies")
            db_path = request.getfixturevalue("scratch_db")[0]
        if is_anonymous(handoff_page):
            cookies = []
        opener = _opener_for(handoff_page, db_path)
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
    if handoff_page in OVERLAY_DIALOGS:
        return OVERLAY_DIALOGS[handoff_page]
    if handoff_page not in OPENER_PAGES and handoff_page not in STATE_PAGES:
        return None
    conn = get_connection(Settings(_env_file=None, database_url=f"sqlite:///{db_path.as_posix()}"))
    try:
        return state_opener_url(handoff_page, conn) or opener_url(handoff_page, conn)
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
        if handoff_page in FORM_SUBMITS:
            fields = FORM_SUBMITS[handoff_page]
            for selector, value in fields:
                pg.fill(selector, value)
            with pg.expect_navigation(wait_until="networkidle", timeout=15000):
                pg.press(fields[-1][0], "Enter")
        if opener:
            pg.evaluate(
                "url => window.htmx.ajax('GET', url, {target: '#modal-root', swap: 'innerHTML'})",
                opener,
            )
            pg.wait_for_selector("#modal-root dialog[open]", timeout=15000)
            if handoff_page in DIALOG_SUBMITS:
                submit_dialog(pg, handoff_page)
            elif (state := state_recipe(handoff_page)) is not None:
                state(pg)  # a dialog the user has worked on (handoff_recurring)
        elif (recipe := click_recipe(handoff_page)) is not None:
            recipe(pg)  # client-side overlay: the click or key a user makes (handoff_clicks)
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
