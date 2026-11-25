"""Browser recipes of the handoff page states that need a request, not a URL (T-UR00b, ADR-0147).

A handoff page such as ``errors/409`` or ``today--flash`` is a state the app reaches by an action:
a failing POST, an aborted request, a saved write. Each recipe here drives the loaded app page the
way a user (or the browser) does, so the app's own handler or fragment renders the state; nothing
is injected into the DOM. The page is already loaded at its route (``test_reference.PAGE_ROUTES``);
the caller applies ``FREEZE_CSS`` and screenshots afterwards (the same hook as ``handoff_clicks``).

The 409 and 500 pages use the dev failure routes (``POST /dev/shell/fail/<status>``, mounted while
``BUDGET_ENV`` is not production, which the visual server never sets), submitted as a plain form so
the browser navigates to the error page the real handler renders. The flash page makes the same
dev routes answer through HTMX (the flash regions of the live shell). Offline aborts the HTMX GET
of the upcoming list (``rd/js/offline.js`` shows the state on ``htmx:sendError``). The
first-run setup page needs a database with no users and the setup token hash in the server env.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Final

from playwright.sync_api import Page, Route

from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations

Recipe = Callable[[Page], None]

_TIMEOUT_MS: Final = 15000
# Typed into the Security card: a valid new value twice, a wrong current one.
NEW_VALUE: Final = "fresh-value-12345"
WRONG_VALUE: Final = "not-the-current-one"
# The token the setup page is opened with; only its sha256 reaches the server (ADR-0134 section 9).
SETUP_TOKEN: Final = "handoff-setup-token"  # noqa: S105 — a scratch-server fixture value
SETUP_ROUTE: Final = f"/setup?token={SETUP_TOKEN}"
SETUP_ENV: Final = "BUDGET_PLANNER_SETUP_TOKEN_HASH"
# Register pages: the app answers the first-run form only on a DB with no users.
NO_USER_PAGES: Final = frozenset({"pages/auth/register.html", "pages/auth/register--error.html"})


def _post_form(page: Page, path: str) -> None:
    """Submit a plain POST form (CSRF token from the page meta) and wait for the answer page."""
    with page.expect_navigation(wait_until="networkidle", timeout=_TIMEOUT_MS):
        page.evaluate(
            """path => {
                const form = document.createElement('form');
                form.method = 'post';
                form.action = path;
                const token = document.createElement('input');
                token.type = 'hidden';
                token.name = '_csrf_token';
                token.value = window.budgetCsrf.token();
                form.append(token);
                document.body.append(form);
                form.submit();
            }""",
            path,
        )


def _conflict(page: Page) -> None:
    _post_form(page, "/dev/shell/fail/409")


def _server_error(page: Page) -> None:
    _post_form(page, "/dev/shell/fail/500")


def _offline(page: Page) -> None:
    """The upcoming range control with the network gone: the state shows in the flash region."""

    def refuse(route: Route) -> None:
        route.abort("internetdisconnected")

    page.route("**/today/upcoming*", refuse)
    page.click("#upcoming .rd-segmented__option[hx-get*='window=30']")
    page.wait_for_selector("#main [data-js='offline-state']", timeout=_TIMEOUT_MS)
    page.unroute("**/today/upcoming*")


def _afford_250(page: Page) -> None:
    """The handoff's Today boards show the afford check typed with 250.00 and answered."""
    page.fill("#afford", "250.00")
    page.wait_for_selector("#afford-result .rd-afford__result", timeout=_TIMEOUT_MS)
    page.evaluate("document.activeElement.blur()")


def _flash(page: Page) -> None:
    """The handoff's flash board: afford check, a saved write, a failed one and a toast."""
    _afford_250(page)
    for path, region in (
        ("/dev/shell/dialog/confirm", "#flash-region .rd-flash--success"),
        ("/dev/shell/fail/500", "#flash-region-assertive .rd-flash--error"),
        ("/dev/shell/toast", "#toast-root [data-js='toast']"),
    ):
        page.evaluate(
            "url => window.htmx.ajax('POST', url, {swap: 'none'})",
            path,
        )
        page.wait_for_selector(region, timeout=_TIMEOUT_MS)


def _loading(page: Page) -> None:
    """The upcoming section while its list request is in flight (the request is held)."""
    _afford_250(page)
    held: list[Route] = []

    def hold(route: Route) -> None:
        held.append(route)  # never fulfilled: the request stays pending

    page.route("**/today/upcoming*", hold)
    page.click("#upcoming .rd-segmented__option[hx-get*='window=30']")
    page.wait_for_selector("#upcoming.htmx-request", timeout=_TIMEOUT_MS)


def _fill_submit(page: Page, fills: tuple[tuple[str, str], ...]) -> None:
    for selector, value in fills:
        page.fill(selector, value)
    with page.expect_navigation(wait_until="networkidle", timeout=_TIMEOUT_MS):
        page.press(fills[-1][0], "Enter")


def _setup_invalid(page: Page) -> None:
    """The first-run form refused: a short email-less draft, typed as the handoff shows it."""
    page.eval_on_selector("form", "f => f.setAttribute('novalidate', '')")
    _fill_submit(
        page,
        (
            ("input[name=email]", "owner@example"),
            ("input[name=password]", "short"),
        ),
    )


def _security_error(page: Page) -> None:
    """A wrong current password with a valid new one: HTMX swaps the card form with its error."""
    page.fill("#new-password", NEW_VALUE)
    page.fill("#confirm-password", NEW_VALUE)
    page.fill("#current-password", WRONG_VALUE)
    page.press("#current-password", "Enter")
    page.wait_for_selector("#current-password-error", timeout=_TIMEOUT_MS)
    page.evaluate("() => document.activeElement?.blur()")  # the handoff file shows no focus ring


def _force_invalid(page: Page) -> None:
    """The forced-rotation form with two different new passwords (typed as the handoff shows)."""
    page.fill("#new-password", "twelve-chars")
    page.fill("#confirm-password", "ten-chars!")
    page.press("#confirm-password", "Enter")
    page.wait_for_selector("#confirm-password-error", timeout=_TIMEOUT_MS)


def _theme_chosen(page: Page) -> None:
    """The handoff renders with ``?theme=<scheme>``, so its switch shows that scheme pressed.

    The app stores the choice client-side (``rd-theme``); the user's click is the equivalent.
    """
    dark = page.evaluate("window.matchMedia('(prefers-color-scheme: dark)').matches")
    page.click(f"[data-theme-value='{'dark' if dark else 'light'}']")


# Handoff page -> recipe run after the page's route is loaded.
RECIPES: Final[dict[str, Recipe]] = {
    "pages/errors/409.html": _conflict,
    "pages/errors/500.html": _server_error,
    "pages/errors/offline.html": _offline,
    "pages/today--flash.html": _flash,
    "pages/today--loading.html": _loading,
    "pages/auth/register--error.html": _setup_invalid,
    "pages/auth/force-password--error.html": _force_invalid,
    "pages/settings/preferences.html": _theme_chosen,
    "pages/settings/security--error.html": _security_error,
}


def state_recipe(page: str) -> Recipe | None:
    """The recipe of a handoff page, None when its route alone shows the state."""
    return RECIPES.get(page)


def build_empty_db(db_path: Path) -> None:
    """A migrated scratch DB with no user (first-run state); never an existing or prod file."""
    if db_path.exists():
        raise FileExistsError(f"{db_path} exists; scratch DBs are built fresh")
    conn: sqlite3.Connection = get_connection(
        Settings(_env_file=None, database_url=f"sqlite:///{db_path.as_posix()}")
    )
    try:
        apply_migrations(conn)
    finally:
        conn.close()


def setup_server_env() -> dict[str, str]:
    """Server env of the first-run page: the dev bootstrap admin is off, the token hash is set.

    ``BUDGET_ENV=dev`` creates the default admin at start-up, which closes setup; ``test`` does
    not, and the setup page needs only the hash of ``SETUP_TOKEN`` (ADR-0134 section 9).
    """
    return {"BUDGET_ENV": "test", SETUP_ENV: hashlib.sha256(SETUP_TOKEN.encode()).hexdigest()}
