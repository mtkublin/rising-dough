"""Route-coverage allowlists (T-UT03, ADR-0106 section 1).

``FRAMEWORK`` is permanent. ``PENDING_T_UT04x`` shrink to empty: when a
T-UT04x item adds ``@covers`` tests for a route it deletes that route's line
here (and the whole section when empty). Sections are separate dicts so
parallel items touch disjoint hunks. ``ALLOWLIST`` is their union.
"""

from __future__ import annotations

from typing import Final

FRAMEWORK: Final[dict[str, str]] = {
    "GET /openapi.json": "framework",
    "GET /docs": "framework",
    "GET /docs/oauth2-redirect": "framework",
    "MOUNT /static": "framework",
}

# --- T-UT04c: ledger ---
PENDING_T_UT04C: Final[dict[str, str]] = {
    "GET /transactions": "pending T-UT04c",
    "GET /transactions/_limit_preview": "pending T-UT04c",
    "GET /transactions/table": "pending T-UT04c",
    "GET /transactions/new": "pending T-UT04c",
    "POST /transactions": "pending T-UT04c",
    "GET /transactions/{txn_id}/edit": "pending T-UT04c",
    "POST /transactions/{txn_id}": "pending T-UT04c",
    "POST /transactions/{txn_id}/delete": "pending T-UT04c",
    "POST /transactions/{txn_id}/restore": "pending T-UT04c",
    "GET /transactions/export": "pending T-UT04c",
    "GET /planned": "pending T-UT04c",
    "POST /planned/batch/promote-due": "pending T-UT04c",
    "POST /planned/batch/undo": "pending T-UT04c",
    "GET /planned/table": "pending T-UT04c",
    "GET /planned/new": "pending T-UT04c",
    "POST /planned": "pending T-UT04c",
    "GET /planned/{planned_id}/edit": "pending T-UT04c",
    "POST /planned/{planned_id}": "pending T-UT04c",
    "POST /planned/{planned_id}/delete": "pending T-UT04c",
    "POST /planned/{planned_id}/restore": "pending T-UT04c",
    "GET /planned/{planned_id}/promote": "pending T-UT04c",
    "GET /planned/{planned_id}/promote/inline": "pending T-UT04c",
    "POST /planned/{planned_id}/promote": "pending T-UT04c",
    "GET /planned/export": "pending T-UT04c",
    "GET /recurring": "pending T-UT04c",
    "GET /recurring/new": "pending T-UT04c",
    "POST /recurring": "pending T-UT04c",
    "POST /recurring/batch/promote-due": "pending T-UT04c",
    "POST /recurring/batch/undo": "pending T-UT04c",
    "POST /recurring/formula/preview": "pending T-UT04c",
    "GET /recurring/{rule_id}/edit": "pending T-UT04c",
    "POST /recurring/{rule_id}": "pending T-UT04c",
    "POST /recurring/{rule_id}/deactivate": "pending T-UT04c",
    "GET /recurring/{rule_id}/overrides/new": "pending T-UT04c",
    "POST /recurring/{rule_id}/overrides": "pending T-UT04c",
    "POST /recurring/{rule_id}/overrides/{occurrence_date}/delete": "pending T-UT04c",
    "GET /recurring/{rule_id}/promote": "pending T-UT04c",
    "GET /recurring/{rule_id}/promote/inline": "pending T-UT04c",
    "POST /recurring/{rule_id}/promote": "pending T-UT04c",
    "POST /recurring/{rule_id}/skip-next": "pending T-UT04c",
    "GET /ledger": "pending T-UT04c",
    "GET /ledger/table": "pending T-UT04c",
    "GET /ledger/recently-deleted": "pending T-UT04c",
}

# --- T-UT04d: plan ---
PENDING_T_UT04D: Final[dict[str, str]] = {
    "GET /budget/yearly": "pending T-UT04d",
    "GET /budget/rules/{category_id}/overrides/new": "pending T-UT04d",
    "POST /budget/rules/{category_id}/overrides": "pending T-UT04d",
    "GET /budget": "pending T-UT04d",
    "GET /budget/manage": "pending T-UT04d",
    "POST /budget/defaults/{category_id}": "pending T-UT04d",
    "POST /budget/recurring/{category_id}/{month}": "pending T-UT04d",
    "POST /budget/preferences/income-anchor": "pending T-UT04d",
    "POST /budget/one-off/{category_id}/{year}/{month}": "pending T-UT04d",
    "GET /forecast": "pending T-UT04d",
    "GET /forecast/view": "pending T-UT04d",
    "GET /analytics": "pending T-UT04d",
    "GET /plan": "pending T-UT04d",
    "GET /plan/analytics": "pending T-UT04d",
    "GET /budget-legacy": "pending T-UT04d",
}

# --- T-UT04e: settings ---
PENDING_T_UT04E: Final[dict[str, str]] = {
    "GET /categories": "pending T-UT04e",
    "GET /categories/new": "pending T-UT04e",
    "POST /categories": "pending T-UT04e",
    "GET /categories/{category_id}/edit": "pending T-UT04e",
    "POST /categories/{category_id}": "pending T-UT04e",
    "POST /categories/{category_id}/delete": "pending T-UT04e",
    "POST /categories/{category_id}/archive": "pending T-UT04e",
    "POST /categories/{category_id}/restore": "pending T-UT04e",
    "GET /settings": "pending T-UT04e",
    "GET /settings/close": "pending T-UT04e",
    "GET /settings/users": "pending T-UT04e",
    "POST /settings/users": "pending T-UT04e",
    "GET /settings/users/{user_id}/edit": "pending T-UT04e",
    "POST /settings/users/{user_id}": "pending T-UT04e",
    "POST /settings/users/{user_id}/reset-password": "pending T-UT04e",
    "POST /settings/users/{user_id}/delete": "pending T-UT04e",
    "GET /settings/password": "pending T-UT04e",  # pragma: allowlist secret
    "POST /settings/password": "pending T-UT04e",  # pragma: allowlist secret
    "GET /settings/security": "pending T-UT04e",
}

ALLOWLIST: Final[dict[str, str]] = {
    **FRAMEWORK,
    **PENDING_T_UT04C,
    **PENDING_T_UT04D,
    **PENDING_T_UT04E,
}
