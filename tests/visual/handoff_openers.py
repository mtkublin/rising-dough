"""Dialog openers of the handoff overlay pages (T-UR00b remainder, UR00f, ADR-0147).

A handoff overlay page is the Today board with one dialog open. The app opens the same
dialog from a GET (new-entry via ``/add?dialog=1``, every other one through the dialog
route the real opener button calls). ``opener_url`` resolves the id-bound routes from the
handoff seed (entities found by name in the scratch DB, never by a typed id), so the
comparison loads ``/today`` and fetches the dialog into ``#modal-root`` the way HTMX does
(``tests/e2e/test_csp_buttons.py`` uses the same call).

Read-only: it only lists entities of the seeded scratch DB through the repositories.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Final

from budget_planner.domain.planned import PlannedFilter
from budget_planner.domain.transactions import TransactionFilter
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
    recurring as recurring_repo,
    transactions as transactions_repo,
    users as users_repo,
)
from budget_planner.services import invites as invites_service

OWNER_ID: Final = 1

# page stem -> (route template, query). Placeholders: {account:<name>}, {category:<name>},
# {user:<email>}, {invite:<email>}, {planned:<description>}, {rule:<description>@<next due>},
# {txn:<description>@<day>@<minor>}.
OPENERS: Final[dict[str, str]] = {
    "new-account": "/accounts/new",
    "edit-account": "/accounts/{account:Investments A}/edit",
    "edit-account--liability": "/accounts/{account:Investments A}/edit",
    "delete-account--blocked": "/accounts/{account:Checking}/edit?intent=delete",
    "delete-account": "/accounts/{account:Investments E}/edit?intent=delete",
    "delete-account--blocked-planned": "/accounts/{account:Investments D}/edit?intent=delete",
    "new-account--filled": "/accounts/new",
    "new-account--error": "/accounts/new",
    "new-category--filled": "/categories/new",
    "new-category--error": "/categories/new",
    "reconcile": "/accounts/{account:Checking}/reconcile",
    "reconcile--liability": "/accounts/{account:Credit Card}/reconcile",
    "new-category": "/categories/new",
    "edit-category": "/categories/{category:Takeaway}/edit",
    "archive-category": "/categories/{category:Takeaway}/archive",
    "edit-planned": "/planned/{planned:Car}/edit",
    "promote--planned": "/planned/{planned:Car}/promote",
    "edit-recurring--fixed": "/recurring/{rule:Fixed Costs@2026-11-01}/edit",
    "edit-recurring--formula": "/recurring/{rule:Taxes@2026-11-12}/edit",
    "promote--recurring": "/recurring/{rule:Fixed Costs@2026-11-01}/promote",
    "override--occurrence": (
        "/recurring/{rule:Fixed Costs@2026-11-01}/overrides/new?occurrence_date=2026-11-01"
    ),
    "override--budget-month": (
        "/budget/rules/{category:Big Purchases}/overrides/new?year=2026&month=10&tier=one-off"
    ),
    "override--budget-every": (
        "/budget/rules/{category:Big Purchases}/overrides/new?year=2026&month=10&tier=recurring"
    ),
    "override--budget-default": (
        "/budget/rules/{category:Big Purchases}/overrides/new?year=2026&month=10&tier=default"
    ),
    "edit-transaction": "/transactions/{txn:Takeaway@2026-10-31@3550}/edit",
    "edit-transaction--transit": "/transactions/{txn:Transit@2026-10-26@2193}/edit",
    # Settings users board. The POST states (`handoff_forms.DIALOG_SUBMITS`) open the same
    # dialog and then submit the typed values in the browser.
    "add-user": "/settings/users/new",
    "add-user--error": "/settings/users/new",
    "edit-user": "/settings/users/{user:partner@example.test}/edit",
    "delete-user": "/settings/users/{user:partner@example.test}/delete",
    "reset-password": "/settings/users/{user:partner@example.test}/reset-password",
    "one-time-password": "/settings/users/{user:partner@example.test}/reset-password",
    "invite-user": "/settings/users/invites/new",
    "invite-user--error": "/settings/users/invites/new",
    "revoke-invite": "/settings/users/invites/{invite:accountant@example.test}/revoke",
}


def _account_id(conn: sqlite3.Connection, name: str) -> int:
    return next(a.id for a in accounts_repo.list_all(conn, OWNER_ID) if a.name == name)


def _category_id(conn: sqlite3.Connection, name: str) -> int:
    return next(c.id for c in categories_repo.list_all(conn, OWNER_ID) if c.name == name)


def _planned_id(conn: sqlite3.Connection, description: str) -> int:
    rows = planned_repo.list_filtered(conn, OWNER_ID, PlannedFilter())
    return next(p.id for p in rows if p.description == description)


def _rule_id(conn: sqlite3.Connection, spec: str) -> int:
    description, due = spec.split("@")
    rules = recurring_repo.list_rules(conn, OWNER_ID)
    return next(
        r.id
        for r in rules
        if r.default_description == description and r.next_due == date.fromisoformat(due)
    )


def _txn_id(conn: sqlite3.Connection, spec: str) -> int:
    description, day, minor = spec.split("@")
    rows = transactions_repo.list_filtered(conn, OWNER_ID, TransactionFilter())
    return next(
        t.id
        for t in rows
        if t.description == description
        and t.operation_date == date.fromisoformat(day)
        and t.amount == int(minor)
    )


def _user_id(conn: sqlite3.Connection, email: str) -> int:
    return next(u.id for u in users_repo.list_live(conn) if u.email == email)


def _invite_id(conn: sqlite3.Connection, email: str) -> int:
    return next(i.id for i in invites_service.list_invites(conn) if i.email == email)


_RESOLVERS: Final = {
    "user": _user_id,
    "invite": _invite_id,
    "account": _account_id,
    "category": _category_id,
    "planned": _planned_id,
    "rule": _rule_id,
    "txn": _txn_id,
}


def opener_url(page: str, conn: sqlite3.Connection) -> str | None:
    """The dialog route of an overlay page (``pages/overlays/<stem>.html``), ids resolved."""
    template = OPENERS.get(page.removeprefix("pages/overlays/").removesuffix(".html"))
    if template is None:
        return None
    out = template
    while "{" in out:
        start = out.index("{")
        end = out.index("}", start)
        kind, _, arg = out[start + 1 : end].partition(":")
        out = f"{out[:start]}{_RESOLVERS[kind](conn, arg)}{out[end + 1 :]}"
    return out
