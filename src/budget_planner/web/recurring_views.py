"""Recurring page render helpers (T-Q266): form-error, promote-modal and row values.

Moved out of the recurring router; services supply the values, ``render`` builds the response.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import date

from fastapi import Request
from fastapi.responses import Response

from budget_planner.domain.recurring import RecurringOverride, RecurringRule
from budget_planner.services import (
    accounts as accounts_service,
    categories as categories_service,
    recurring as recurring_svc,
    recurring_formula as formula_svc,
)
from budget_planner.web.recurring_forms import TermInput, formula_source_candidates
from budget_planner.web.rendering import render

_FORM_TEMPLATE = "partials/recurring/_form.html"
_PROMOTE_MODAL = "partials/recurring/_promote_modal.html"


def render_form_errors(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    *,
    rule: RecurringRule | None,
    action: str,
    errors: Mapping[str, str],
    amount_source: str,
    terms: list[TermInput],
) -> Response:
    return render(
        request,
        _FORM_TEMPLATE,
        rule=rule,
        action=action,
        categories=categories_service.list_all(conn, user_id),
        accounts=accounts_service.list_all(conn, user_id),
        source_categories=formula_source_candidates(conn, user_id),
        amount_source=amount_source,
        terms=terms,
        errors=errors,
        status_code=422,
    )


def effective_amount_for_render(
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
) -> int:
    """Return the amount to render in the Ledger row for a rule (formula-aware)."""
    return formula_svc.resolve_rule_amount(conn, user_id, rule, rule.next_due)


def override_on_next_due(
    conn: sqlite3.Connection,
    user_id: int,
    rule_id: int,
    next_due: date,
) -> RecurringOverride | None:
    """Return the override whose canonical ``occurrence_date == next_due``."""
    for override in recurring_svc.list_overrides(conn, user_id, rule_id):
        if override.occurrence_date == next_due:
            return override
    return None


def render_promote_modal(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    rule_id: int,
    *,
    errors: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return render(
            request,
            _PROMOTE_MODAL,
            rule=None,
            account=None,
            override=None,
            prefill_date=None,
            prefill_amount_minor=None,
            prefill_description="",
            errors={"rule": "not found"},
            status_code=404,
        )
    override = override_on_next_due(conn, user_id, rule_id, rule.next_due)
    account = accounts_service.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    prefill_date = rule.next_due
    prefill_amount = formula_svc.resolve_rule_amount(conn, user_id, rule, rule.next_due)
    prefill_description = rule.default_description
    if override is not None:
        if override.date_override is not None:
            prefill_date = override.date_override
        if override.amount_override is not None:
            prefill_amount = override.amount_override
        if override.description_override is not None:
            prefill_description = override.description_override
    return render(
        request,
        _PROMOTE_MODAL,
        rule=rule,
        account=account,
        override=override,
        prefill_date=prefill_date,
        prefill_amount_minor=prefill_amount,
        prefill_description=prefill_description,
        errors=errors or {},
        status_code=status_code,
    )
