"""App route -> handoff page (target ``mockup``; ADR-0106 sections 2 and 5).

Seeded from ``docs/plans/ui-test-harness/parity.md``: for every ``mapped`` row
with a ``GET`` route, the primary handoff page for that route (the first
state listed). Paths are relative to ``docs/design/rising-dough-frontend/``.
Path templates keep the app's ``{param}`` placeholders; the mockup has fixed
sample data, so ``handoff_page`` ignores parameter values. Query strings that
select a state (``?tab=``, ``?view=``) are part of the key.
"""

from __future__ import annotations

import re
from pathlib import Path

HANDOFF_ROOT = Path(__file__).resolve().parents[2] / "docs" / "design" / "rising-dough-frontend"

ROUTES: dict[str, str] = {
    "/": "pages/today.html",
    "/add": "pages/overlays/new-entry--happened.html",
    "/auth/login": "pages/auth/login.html",
    "/auth/reauth": "pages/auth/reauth.html",
    "/auth/register": "pages/settings/security.html",
    "/auth/sessions": "pages/settings/security.html",
    "/today": "pages/today.html",
    "/dev/shell": "pages/today.html",  # T-UR02 placeholder page on the new base
    "/dev/shell?view=theme": "pages/settings/preferences.html",
    "/today/upcoming": "pages/today.html",
    "/planned/{planned_id}/promote/inline": "pages/overlays/promote--planned.html",
    "/recurring/{rule_id}/promote/inline": "pages/overlays/promote--recurring.html",
    "/today/afford": "pages/today.html",
    "/afford": "pages/today.html",
    "/ledger": "pages/ledger/actual.html",
    "/ledger/table": "pages/ledger/actual.html",
    "/transactions/table": "pages/ledger/actual.html",
    "/ledger?view=planned": "pages/ledger/planned.html",
    "/ledger?view=recurring": "pages/ledger/recurring.html",
    "/planned/table": "pages/ledger/planned.html",
    "/ledger/recently-deleted": "pages/ledger/recently-deleted.html",
    "/transactions": "pages/ledger/actual.html",
    "/planned": "pages/ledger/planned.html",
    "/recurring": "pages/ledger/recurring.html",
    "/transactions/new": "pages/overlays/new-entry--happened.html",
    "/transactions/{txn_id}/edit": "pages/overlays/edit-transaction.html",
    "/planned/new": "pages/overlays/new-entry--planned.html",
    "/planned/{planned_id}/edit": "pages/overlays/edit-planned.html",
    "/planned/{planned_id}/promote": "pages/overlays/promote--planned.html",
    "/recurring/new": "pages/overlays/new-entry--repeats-fixed.html",
    "/recurring/{rule_id}/edit": "pages/overlays/edit-recurring--fixed.html",
    "/recurring/{rule_id}/overrides/new": "pages/overlays/override--occurrence.html",
    "/recurring/{rule_id}/promote": "pages/overlays/promote--recurring.html",
    "/plan": "pages/plan/budget.html",
    "/plan?tab=budget": "pages/plan/budget.html",
    "/budget/rules/{category_id}/overrides/new": "pages/overlays/override--budget-month.html",
    "/plan?tab=year": "pages/plan/year.html",
    "/budget/yearly": "pages/plan/year.html",
    "/plan?tab=forecast": "pages/plan/forecast.html",
    "/forecast": "pages/plan/forecast.html",
    "/forecast/view": "pages/plan/forecast.html",
    "/plan/analytics": "pages/plan/analytics.html",
    "/plan?tab=analytics": "pages/plan/analytics.html",
    "/budget": "pages/plan/budget.html",
    "/budget/manage": "pages/plan/budget.html",
    "/budget-legacy": "pages/plan/budget.html",
    "/analytics": "pages/plan/budget.html",
    "/accounts": "pages/accounts.html",
    "/accounts?state=empty": "pages/accounts--empty.html",  # app: no accounts yet
    "/accounts/last-checked": "pages/accounts.html",
    "/accounts/new": "pages/overlays/new-account.html",
    "/accounts/{account_id}/edit": "pages/overlays/edit-account.html",
    "/accounts/{account_id}/reconcile": "pages/overlays/reconcile.html",
    "/settings": "pages/settings/categories.html",
    "/settings/close": "pages/settings/categories.html",
    "/settings?tab=categories": "pages/settings/categories.html",
    "/categories/new": "pages/overlays/new-category.html",
    "/categories/{category_id}/edit": "pages/overlays/edit-category.html",
    "/categories": "pages/settings/categories.html",
    "/settings?tab=fx": "pages/settings/currency-fx.html",
    "/settings?tab=prefs": "pages/settings/preferences.html",
    "/settings/password": "pages/settings/security.html",  # pragma: allowlist secret
    "/settings/security": "pages/settings/security.html",
    "/settings/users": "pages/settings/users.html",
    "/settings/users/{user_id}/edit": "pages/overlays/edit-user.html",
}

_PARAM = re.compile(r"/\d+(?=/|$|\?)")


def _template(route: str) -> str:
    """Turn ``/accounts/7/edit`` into ``/accounts/{id}/edit`` for lookup."""
    return _PARAM.sub("/{}", route)


def handoff_page(route: str) -> str:
    """Handoff page path (relative to the handoff root) for an app ``route``."""
    if route in ROUTES:
        return ROUTES[route]
    wanted = _template(route)
    for key, page in ROUTES.items():
        if re.sub(r"\{[a-z_]+\}", "{}", key) == wanted:
            return page
    raise KeyError(f"no handoff page mapped for app route {route!r}")
