"""Route and recipe mapping of the handoff pages onto app routes (ADR-0154).

Not a test module since T-UR65 (the handoff comparison tests are gone). ``snapshot_routes``
builds the accepted-UI snapshot cases from these tables; ``test_reference_mapping`` pins them.
"""

from __future__ import annotations

import re

from tests.visual import handoff
from tests.visual.handoff_newentry import PHONE_SHEET_DIALOGS
from tests.visual.handoff_openers import OPENERS
from tests.visual.handoff_states import (
    SETUP_ROUTE,
)

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
# The long board: the handoff shows three rows and the "older" link (page size 3).
LEDGER_LONG = "/ledger?date_from=2026-10-07&date_to=2026-10-31&page_size=3"
_NO_MATCHES = LEDGER_BOARD + "&q=pizza"
AFFORD_TYPED = "/today?amount=250.00"
# Pages with their own app route (plan ?tab=, ledger ?view=, settings tabs, auth, errors).
PAGE_ROUTES: dict[str, str] = {
    "pages/plan/year.html": "/plan?tab=year",
    "pages/plan/forecast.html": "/plan?tab=forecast",
    "pages/plan/analytics.html": "/plan?tab=analytics",
    "pages/ledger/actual.html": LEDGER_BOARD,
    "pages/ledger/actual--long.html": LEDGER_LONG,
    "pages/ledger/planned.html": "/ledger?view=planned",
    "pages/ledger/planned--empty.html": "/ledger?view=planned",
    "pages/ledger/recurring.html": "/ledger?view=recurring",
    "pages/ledger/recurring--empty.html": "/ledger?view=recurring",
    "pages/ledger/recently-deleted.html": "/ledger/recently-deleted",
    # The handoff board (4 day groups, 11 rows) with its "pizza" search (category chip needs an id).
    "pages/ledger/actual--no-matches.html": _NO_MATCHES,
    "pages/errors/422.html": "/plan?tab=budget&year=zz&month=zz",
    "pages/settings/preferences.html": "/settings?tab=prefs",
    "pages/settings/currency-fx.html": "/settings?tab=fx",
    "pages/settings/security.html": "/settings/security",
    "pages/settings/security--error.html": "/settings/security",
    # Error pages start from Today; the recipe (handoff_states) reaches the answer page.
    "pages/errors/409.html": "/today",
    "pages/errors/500.html": "/today",
    "pages/errors/offline.html": "/today",
    # GET /today?amount= answers the afford check (an unparsable text; 1,800.00 over the limit).
    "pages/today--afford-invalid.html": "/today?amount=abc",
    "pages/today--afford-over.html": "/today?amount=1800",
    # The handoff Today (and each overlay over it) shows 250.00 typed in the afford field.
    "pages/today.html": AFFORD_TYPED,
    "pages/today--empty.html": AFFORD_TYPED,
    "pages/auth/register.html": SETUP_ROUTE,
    "pages/auth/register--error.html": SETUP_ROUTE,
    "pages/auth/force-password.html": "/settings/password",
    "pages/auth/force-password--error.html": "/settings/password",
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
# Handoff pages (not overlays) the harness cannot reach yet: page -> why. Like UNMAPPED_OVERLAYS
# they are still compared with their surface's fallback route (red); this dict only shrinks.
# Empty since T-UR00b mapped every page: the state recipes are `handoff_states`.
UNMAPPED_PAGES: dict[str, str] = {}
# Overlay pages whose dialog the app opens from a plain GET (the new-entry dialog,
# `/add?when=<tab>`, T-UR07b). Like every opener it is fetched into #modal-root over the
# overlay's base page (Today), never loaded as a blank shell.
OVERLAY_DIALOGS: dict[str, str] = {
    "pages/overlays/new-entry--happened.html": "/add?when=happened",
    "pages/overlays/new-entry--planned.html": "/add?when=planned",
    "pages/overlays/new-entry--repeats-fixed.html": "/add?when=repeats",
    # The phone sheet is the happened dialog (the handoff file has the same markup).
    **PHONE_SHEET_DIALOGS,
}
# Overlay pages whose dialog the app opens from a dialog route (id-bound ones resolved from
# the seed): `handoff_openers.OPENERS`; the test loads the overlay's base page and fetches it
# into #modal-root.
# Overlay pages with no way to open their state yet: the year-cell inline editor, which the
# app does not have (compared against the plain base page, red). Every other overlay is
# mapped: dialogs (OVERLAY_DIALOGS, OPENERS), clicks, new-entry and state recipes.
UNMAPPED_OVERLAYS: frozenset[str] = frozenset()
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
    # The handoff categories board lacks the 18th expense category of the base seed. Overlays over
    # it (edit, archive, new category) take the same modifier through `base_page_of`.
    "pages/settings/categories.html": ("settings-categories",),
    "pages/auth/invite--expired.html": ("invite-expired",),
    "pages/auth/invite--used.html": ("invite-used",),
    # Fresh DB per run: the wrong-password POST must not eat a shared rate limit.
    "pages/auth/login--error.html": ("form-error",),
    "pages/auth/reauth--error.html": ("form-error",),
    "pages/settings/security--error.html": ("form-error",),
    "pages/auth/force-password.html": ("owner-must-change",),
    "pages/auth/force-password--error.html": ("owner-must-change",),
}
# Overlays whose dialog needs data the base page does not have (an account nothing points at,
# an account with recurring rules); the modifier applies to that overlay only.
OVERLAY_MODIFIERS: dict[str, tuple[str, ...]] = {
    "pages/overlays/delete-account.html": ("unreferenced-account",),
    "pages/overlays/delete-account--blocked-planned.html": ("account-with-rules",),
    # D1-c(i): the board's picker lists 20 categories; the four it lacks are archived.
    "pages/overlays/category-picker.html": ("picker-handoff-list",),
    "pages/overlays/category-picker--no-match.html": ("picker-handoff-list",),
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
    return OVERLAY_MODIFIERS.get(page) or PAGE_MODIFIERS.get(base_page_of(page), ())
