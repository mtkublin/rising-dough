"""Recurring page render helpers (T-Q266): form-error, promote-modal and row values.

Moved out of the recurring router; services supply the values, ``render`` builds the response.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import date

from fastapi import Request
from fastapi.responses import HTMLResponse, Response

from budget_planner.domain.accounts import Account
from budget_planner.domain.categories import Category
from budget_planner.domain.money import format_major
from budget_planner.domain.recurring import RecurringOverride, RecurringRule
from budget_planner.services import (
    accounts as accounts_service,
    categories as categories_service,
    recurring as recurring_svc,
    recurring_formula as formula_svc,
)
from budget_planner.services.recurring_formula import FormulaFx
from budget_planner.web.dialogs import dialog_response, invalid_dialog_response
from budget_planner.web.entry_forms import promote_context
from budget_planner.web.form_responses import (
    PROMOTE_TEMPLATE,
    from_dialog,
    new_entry_errors,
    open_new_entry,
)
from budget_planner.web.htmx import Event, refresh_unless_on, trigger
from budget_planner.web.params import parse_int
from budget_planner.web.paths import LEDGER_PATH
from budget_planner.web.recurring_forms import (
    EMPTY_TERM_INPUT,
    OverrideError,
    RuleFields,
    TermInput,
    formula_source_candidates,
    month_or,
    year_or,
)
from budget_planner.web.rendering import SLIDEOVER_TEMPLATE, render

_FORM_TEMPLATE = "partials/recurring/_form.html"
_OVERRIDE_FORM = "partials/recurring/_override_form.html"
CREATE_ACTION = "/recurring"
_LEGACY_PROMOTE = "partials/recurring/_promote_modal.html"
_ROW = "partials/recurring/_row.html"
_PROMOTE_INLINE_ROW = "partials/recurring/_promote_inline_row.html"


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
    fx: FormulaFx,
) -> int:
    """Return the amount to render in the Ledger row for a rule (formula-aware)."""
    return formula_svc.resolve_rule_amount(conn, user_id, rule, rule.next_due, fx=fx)


def preview_currency(
    conn: sqlite3.Connection,
    user_id: int,
    posted_account_id: object,
    draft_rule_id: int | None,
    fx: FormulaFx,
) -> str:
    """Currency the draft formula is shown in: form account, else draft rule's, else base."""
    account_id = parse_int(str(posted_account_id or ""))
    if account_id is None and draft_rule_id is not None:
        draft = recurring_svc.find_rule(conn, user_id, draft_rule_id)
        account_id = draft.account_id if draft is not None else None
    acc = (
        accounts_service.find_by_id(conn, user_id, account_id, include_deleted=True)
        if account_id is not None
        else None
    )
    return acc.currency if acc is not None else fx.converter.base_currency


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


def _promote_prefill(
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
    override: RecurringOverride | None,
    fx: FormulaFx,
) -> tuple[date, int, str]:
    """Date, amount and note the promote dialog opens with: the rule's, or the override's."""
    amount = formula_svc.resolve_rule_amount(conn, user_id, rule, rule.next_due, fx=fx)
    if override is None:
        return rule.next_due, amount, rule.default_description
    return (
        override.date_override or rule.next_due,
        amount if override.amount_override is None else override.amount_override,
        rule.default_description
        if override.description_override is None
        else override.description_override,
    )


def _promote_notes(rule: RecurringRule, override: RecurringOverride | None) -> list[str]:
    """Status lines above the promote fields (override applied, last occurrence)."""
    notes = []
    if override is not None and override.state.value == "overridden":
        notes.append("Override applied for this occurrence.")
    if rule.end_date and rule.next_due == rule.end_date:
        notes.append("Last occurrence: the rule deactivates after promote.")
    return notes


def _legacy_promote(
    request: Request,
    *,
    rule: RecurringRule,
    account: Account | None,
    override: RecurringOverride | None,
    prefill: tuple[date, int, str],
    errors: dict[str, str] | None,
) -> Response:
    """The old shell's promote slide-over (ledger) until T-UR09 / T-UR10."""
    return render(
        request,
        _LEGACY_PROMOTE,
        rule=rule,
        account=account,
        override=override,
        prefill_date=prefill[0],
        prefill_amount_minor=prefill[1],
        prefill_description=prefill[2],
        errors=errors or {},
        status_code=422 if errors else 200,
    )


def render_promote_modal(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    rule_id: int,
    fx: FormulaFx,
    *,
    as_dialog: bool | None = None,
    errors: dict[str, str] | None = None,
    posted: Mapping[str, str] | None = None,
) -> Response:
    """The promote dialog for a rule's next occurrence: prefill (200) or posted values (422).

    The old shell (ledger) still gets its slide-over until T-UR09 / T-UR10 (``as_dialog`` false);
    ``None`` follows the post (``from_dialog``).
    """
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="rule: not found")
    override = override_on_next_due(conn, user_id, rule_id, rule.next_due)
    account = accounts_service.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    prefill = _promote_prefill(conn, user_id, rule, override, fx)
    if not (from_dialog(request) if as_dialog is None else as_dialog):
        return _legacy_promote(
            request, rule=rule, account=account, override=override, prefill=prefill, errors=errors
        )
    context = promote_context(
        conn,
        user_id,
        action=f"{CREATE_ACTION}/{rule.id}/promote",
        category_id=rule.category_id,
        account=account,
        amount_minor=prefill[1],
        date_value=prefill[0],
        note_value=prefill[2],
        base_currency=request.app.state.settings.base_currency,
        recurring=True,
        notes=_promote_notes(rule, override),
        posted=posted,
    )
    if errors:
        return invalid_dialog_response(request, PROMOTE_TEMPLATE, context, errors)
    return dialog_response(request, PROMOTE_TEMPLATE, context)


def render_rule_form_errors(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    *,
    rule: RecurringRule | None,
    action: str,
    fields: RuleFields,
    errors: Mapping[str, str],
) -> Response:
    """Re-render the rule form (422) with the posted terms and the per-field errors."""
    if rule is None and from_dialog(request):
        return new_entry_errors(
            request,
            conn,
            user_id,
            tab="repeats",
            posted={
                "category": fields.category_id,
                "account_id": fields.account_id,
                "dest_account_id": fields.dest_account_id,
                "default_amount": fields.default_amount,
                "start_date": fields.start_date,
                "end_date": fields.end_date,
                "day_of_month": fields.day_of_month,
                "cadence": fields.cadence,
                "amount_source": fields.amount_source,
                "default_description": fields.default_description,
            },
            errors=errors,
            terms=fields.form_terms,
        )
    return render_form_errors(
        request,
        conn,
        user_id,
        rule=rule,
        action=action,
        errors=errors,
        amount_source=fields.amount_source,
        terms=fields.form_terms,
    )


def render_new_form(request: Request, conn: sqlite3.Connection, user_id: int) -> Response:
    """The new-entry dialog on the repeats tab (T-UR07b)."""
    return open_new_entry(request, conn, user_id, tab="repeats")


def render_edit_form(
    request: Request, conn: sqlite3.Connection, user_id: int, rule_id: int
) -> HTMLResponse:
    """Edit slide-over (T-114 / ADR-0030 section 4), mirroring the new-rule form."""
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return render(
            request,
            _FORM_TEMPLATE,
            rule=None,
            action="",
            categories=[],
            accounts=[],
            source_categories=[],
            amount_source="fixed",
            terms=[dict(EMPTY_TERM_INPUT)],
            errors={"rule": "not found"},
            status_code=404,
        )
    amount_source, terms = (
        ("fixed", [dict(EMPTY_TERM_INPUT)])
        if rule.amount_formula is None
        else ("formula", formula_svc.term_input_rows(rule.amount_formula))
    )
    return render(
        request,
        SLIDEOVER_TEMPLATE,
        slide_over_title="Edit recurring rule",
        form_include=_FORM_TEMPLATE,
        rule=rule,
        action=f"/recurring/{rule_id}",
        categories=categories_service.list_all(conn, user_id),
        accounts=accounts_service.list_all(conn, user_id),
        source_categories=formula_source_candidates(conn, user_id),
        amount_source=amount_source,
        terms=terms,
        errors={},
    )


def stale_response(request: Request, *events: Event, refresh_ledger: bool = True) -> Response:
    """Empty response that signals stale views; reload unless the page is the ledger."""
    html = Response()
    trigger(html, *events)
    if refresh_ledger:
        refresh_unless_on(request, html, LEDGER_PATH)
    return html


def render_created_row(
    request: Request,
    rule: RecurringRule,
    account: Account | None,
    category: Category | None,
    effective_amount_minor: int | None,
) -> Response:
    html = render(
        request,
        _ROW,
        rule=rule,
        overrides=[],
        account=account,
        category=category,
        effective_amount_minor=effective_amount_minor,
    )
    trigger(html, Event.FORECAST_STALE, Event.LEDGER_STALE)
    # See create_planned: no row insert; refetch on the ledger, reload elsewhere.
    refresh_unless_on(request, html, LEDGER_PATH)
    return html


def render_rule_row(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
    fx: FormulaFx,
    *events: Event,
) -> Response:
    """Re-render one ledger row for a rule (overrides, account, category, formula amount)."""
    html = render(
        request,
        _ROW,
        rule=rule,
        overrides=recurring_svc.list_overrides(conn, user_id, rule.id),
        account=accounts_service.find_by_id(conn, user_id, rule.account_id, include_deleted=True),
        category=categories_service.find_by_id(
            conn, user_id, rule.category_id, include_deleted=True
        ),
        effective_amount_minor=effective_amount_for_render(conn, user_id, rule, fx),
    )
    trigger(html, *events)
    return html


def render_override_form(
    request: Request, conn: sqlite3.Connection, user_id: int, rule_id: int
) -> Response:
    """Generic override form: year, month and amount default to the rule's ``next_due``."""
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return render(
            request,
            _OVERRIDE_FORM,
            rule=None,
            account=None,
            default_year=None,
            default_month=None,
            default_amount_str=None,
            errors={"rule": "not found"},
            status_code=404,
        )
    account = accounts_service.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    return render(
        request,
        _OVERRIDE_FORM,
        rule=rule,
        account=account,
        default_year=rule.next_due.year,
        default_month=rule.next_due.month,
        default_amount_str=format_major(rule.default_amount, account.currency) if account else "",
        errors={},
    )


def render_override_error(
    request: Request,
    rule: RecurringRule,
    account: Account | None,
    *,
    year: int,
    month: int,
    amount: str,
    error: OverrideError,
) -> Response:
    """T-D151: re-render the override form with the error inside the slide-over."""
    return render(
        request,
        _OVERRIDE_FORM,
        rule=rule,
        account=account,
        default_year=year_or(year, rule.next_due.year),
        default_month=month_or(month, rule.next_due.month),
        default_amount_str=amount,
        errors={error.field: error.message},
        status_code=422,
    )


def render_inline_promote_row(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
    *,
    occurrence: date,
    fx: FormulaFx,
) -> Response:
    """F-02: row-expand inline form for the Today Upcoming Promote action."""
    override = override_on_next_due(conn, user_id, rule.id, occurrence)
    prefill_amount = formula_svc.resolve_rule_amount(conn, user_id, rule, occurrence, fx=fx)
    prefill_description = rule.default_description
    if override is not None:
        if override.amount_override is not None:
            prefill_amount = override.amount_override
        if override.description_override is not None:
            prefill_description = override.description_override
    return render(
        request,
        _PROMOTE_INLINE_ROW,
        rule=rule,
        account=accounts_service.find_by_id(conn, user_id, rule.account_id, include_deleted=True),
        occurrence_date=occurrence,
        prefill_amount_minor=prefill_amount,
        prefill_description=prefill_description,
        categories_by_id={c.id: c for c in categories_service.list_all(conn, user_id)},
    )
