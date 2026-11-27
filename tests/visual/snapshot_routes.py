"""Cases of the accepted-UI snapshot suite (T-UR98, ADR-0154 section 1-2).

One table, no copy of the reference mapping: page routes come from ``test_reference.PAGE_ROUTES`` /
``SURFACE_ROUTES``, dialog routes from ``handoff_openers.OPENERS`` and
``test_reference.OVERLAY_DIALOGS``,
click states from ``handoff_clicks.CLICK_RECIPES``. Data: the handoff base seed at the frozen date.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from tests.visual.handoff import THEMES, VIEWPORTS
from tests.visual.test_reference import (
    ANONYMOUS_PAGES,
    LEDGER_BOARD,
    OVERLAY_DIALOGS,
    PAGE_ROUTES,
    SURFACE_ROUTES,
)


@dataclass(frozen=True)
class SnapshotCase:
    """One screenshot target: a page route, optionally with a dialog or click state on top."""

    name: str
    route: str
    anonymous: bool = False
    dialog_page: str | None = None  # handoff overlay page whose opener/recipe is applied


_PREFIX: Final = "pages/overlays/"


def _page(name: str, handoff_page: str) -> SnapshotCase:
    return SnapshotCase(name, PAGE_ROUTES[handoff_page], anonymous=handoff_page in ANONYMOUS_PAGES)


def _dialog(name: str, overlay: str, base: str) -> SnapshotCase:
    return SnapshotCase(name, base, dialog_page=f"{_PREFIX}{overlay}.html")


PAGES: Final = (
    SnapshotCase("today", SURFACE_ROUTES["today"]),
    SnapshotCase("ledger", LEDGER_BOARD),
    _page("ledger-planned", "pages/ledger/planned.html"),
    _page("ledger-recurring", "pages/ledger/recurring.html"),
    _page("ledger-deleted", "pages/ledger/recently-deleted.html"),
    SnapshotCase("plan-budget", "/plan?tab=budget&year=2026&month=10"),
    _page("plan-year", "pages/plan/year.html"),
    _page("plan-forecast", "pages/plan/forecast.html"),
    _page("plan-analytics", "pages/plan/analytics.html"),
    SnapshotCase("accounts", SURFACE_ROUTES["accounts"]),
    _page("settings-prefs", "pages/settings/preferences.html"),
    SnapshotCase("settings-categories", "/settings?tab=categories"),
    _page("settings-fx", "pages/settings/currency-fx.html"),
    _page("settings-security", "pages/settings/security.html"),
    _page("settings-users", "pages/settings/users.html"),
    _page("login", "pages/auth/login.html"),
    _page("invite", "pages/auth/invite.html"),
    _page("invite-invalid", "pages/auth/invite--invalid.html"),
    SnapshotCase("error-404", SURFACE_ROUTES["errors"]),
    _page("error-422", "pages/errors/422.html"),
)
DIALOGS: Final = (
    _dialog("add-happened", "new-entry--happened", "/today"),
    _dialog("add-planned", "new-entry--planned", "/today"),
    _dialog("add-repeats", "new-entry--repeats-fixed", "/today"),
    _dialog("edit-transaction", "edit-transaction", LEDGER_BOARD),
    _dialog("new-account", "new-account", "/accounts"),
    _dialog("reconcile", "reconcile", "/accounts"),
    _dialog("set-budget", "override--budget-month", "/plan?tab=budget&year=2026&month=10"),
    _dialog("override", "override--occurrence", "/ledger?view=recurring"),
    _dialog("new-category", "new-category", "/settings?tab=categories"),
    _dialog("palette", "command-palette", "/today"),
)
CASES: Final = {case.name: case for case in (*PAGES, *DIALOGS)}
THEME_NAMES: Final = THEMES
VIEWPORT_NAMES: Final = tuple(VIEWPORTS)


def dialog_route(case: SnapshotCase) -> str | None:
    """Static dialog route (new-entry tabs); id-bound ones come from ``handoff_openers``."""
    return OVERLAY_DIALOGS.get(case.dialog_page or "")
