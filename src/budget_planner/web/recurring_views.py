"""Recurring page render helpers (T-Q266): form-error, promote-modal and row values.

Moved out of the recurring router; services supply the values, ``render`` builds the response.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from datetime import date

from fastapi import Request
from fastapi.responses import Response

from budget_planner.domain.accounts import Account
from budget_planner.domain.categories import Category
from budget_planner.domain.money import format_major, format_money
from budget_planner.domain.periods import shift_month
from budget_planner.domain.recurring import RecurringOverride, RecurringRule
from budget_planner.services import (
    accounts as accounts_service,
    categories as categories_service,
    recurring as recurring_svc,
    recurring_formula as formula_svc,
)
from budget_planner.services.recurring_formula import FormulaFx
from budget_planner.web import entry_forms
from budget_planner.web.deps import today_for
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
from budget_planner.web.paths import LEDGER_PATH, PROMOTE_PATH
from budget_planner.web.recurring_forms import (
    EMPTY_TERM_INPUT,
    OverrideError,
    RuleFields,
    TermInput,
    formula_source_candidates,
    parse_terms_from_form,
)
from budget_planner.web.rendering import render, render_context
from budget_planner.web.view_models import month_name

_FORM_TEMPLATE = "partials/recurring/_form.html"
EDIT_TEMPLATE = "fragments/dialogs/edit-recurring.html"
FORMULA_RESULT_TEMPLATE = "fragments/dialogs/formula-result.html"
OCCURRENCE_TEMPLATE = "fragments/dialogs/override-occurrence.html"
OCCURRENCE_REMOVE_TEMPLATE = "fragments/dialogs/override-remove-occurrence.html"
CREATE_ACTION = "/recurring"
_ROW = "partials/recurring/_row.html"
CYCLE_NOTE = "formula cycle: the amount shows 0.00 until the formula is edited to remove the cycle."


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
    return live_amount(conn, user_id, rule, rule.next_due, fx)


def live_amount(
    conn: sqlite3.Connection, user_id: int, rule: RecurringRule, on: date, fx: FormulaFx
) -> int:
    """What the rule posts on ``on``; a stored formula cycle posts 0.00 (Q25, ADR-0047)."""
    return formula_svc.live_rule_amount(conn, user_id, rule, on, fx)[0]


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
    amount = live_amount(conn, user_id, rule, rule.next_due, fx)
    if override is None:
        return rule.next_due, amount, rule.default_description
    return (
        override.date_override or rule.next_due,
        amount if override.amount_override is None else override.amount_override,
        rule.default_description
        if override.description_override is None
        else override.description_override,
    )


def _promote_notes(
    rule: RecurringRule, override: RecurringOverride | None, *, cyclic: bool = False
) -> list[str]:
    """Status lines above the promote fields (formula cycle, override applied, last occurrence)."""
    notes = []
    if cyclic:
        notes.append(CYCLE_NOTE)
    if override is not None and override.state.value == "overridden":
        notes.append("Override applied for this occurrence.")
    if rule.end_date and rule.next_due == rule.end_date:
        notes.append("Last occurrence: the rule deactivates after promote.")
    return notes


def render_promote_modal(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    rule_id: int,
    fx: FormulaFx,
    *,
    errors: dict[str, str] | None = None,
    posted: Mapping[str, str] | None = None,
) -> Response:
    """The promote dialog for a rule's next occurrence: prefill (200) or posted values (422)."""
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="rule: not found")
    override = override_on_next_due(conn, user_id, rule_id, rule.next_due)
    account = accounts_service.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    prefill = _promote_prefill(conn, user_id, rule, override, fx)
    context = promote_context(
        conn,
        user_id,
        action=f"{CREATE_ACTION}/{rule.id}{PROMOTE_PATH}",
        category_id=rule.category_id,
        account=account,
        amount_minor=prefill[1],
        date_value=prefill[0],
        note_value=prefill[2],
        base_currency=request.app.state.settings.base_currency,
        recurring=True,
        notes=_promote_notes(
            rule,
            override,
            cyclic=formula_svc.live_rule_amount(conn, user_id, rule, rule.next_due, fx)[1],
        ),
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


def _rule_values(rule: RecurringRule, account: Account | None) -> dict[str, str]:
    """The stored rule as the dialog's posted text (the amount in its account's currency)."""
    return {
        "category": str(rule.category_id),
        "account_id": str(rule.account_id),
        "dest_account_id": str(rule.dest_account_id or ""),
        "default_amount": format_major(rule.default_amount, account.currency) if account else "",
        "start_date": rule.start_date.isoformat(),
        "end_date": rule.end_date.isoformat() if rule.end_date else "",
        "day_of_month": str(rule.day_of_month or ""),
        "cadence": rule.cadence.value,
        "amount_source": "fixed" if rule.amount_formula is None else "formula",
        "default_description": rule.default_description,
    }


def _drafts(terms: Sequence[Mapping[str, object]]) -> list[formula_svc.DraftTerm]:
    """Term rows as preview drafts; a source id that is not a number is left out."""
    drafts: list[formula_svc.DraftTerm] = []
    for row in terms:
        raw = row.get("source_category_ids")
        ids = [parse_int(str(v)) for v in raw] if isinstance(raw, tuple | list) else []
        drafts.append(
            formula_svc.DraftTerm(
                sign=str(row.get("sign", "+")),
                coefficient_percent=str(row.get("coefficient_percent", "")),
                source_category_ids=tuple(i for i in ids if i is not None),
            )
        )
    return drafts


def edit_context(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
    fx: FormulaFx,
    *,
    posted: Mapping[str, str] | None = None,
    terms: Sequence[Mapping[str, object]] | None = None,
    errors: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """What ``fragments/dialogs/edit-recurring.html`` renders: the stored rule or the posted text.

    A new-entry context for the repeats tab (one builder, so both dialogs agree) plus the rule's
    title, action and id. In formula mode the hero shows the service's next amount for the terms.
    """
    account = accounts_service.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    values = dict(posted) if posted is not None else _rule_values(rule, account)
    rows = _term_rows(rule, terms)
    context = _repeats_context(request, conn, user_id, values=values, rows=rows, errors=errors)
    if values.get("amount_source") == "formula":
        figure = entry_forms.draft_hero(
            conn,
            user_id,
            _drafts(rows),
            currency=str(context["currency"]),
            today=today_for(request),
            fx=fx,
            rule_id=rule.id,
        )
        context = _repeats_context(
            request, conn, user_id, values=values, rows=rows, errors=errors, formula=figure
        )
    category = categories_service.find_by_id(conn, user_id, rule.category_id, include_deleted=True)
    return {
        **_signed_hero(context),
        "title": f"edit recurring rule \N{MIDDLE DOT} {category.name if category else ''}",
        "action": f"{CREATE_ACTION}/{rule.id}",
        "hero_url": f"{CREATE_ACTION}/{rule.id}/edit?hero=1",
        "rule_id": rule.id,
        "selected_dest_id": parse_int(values.get("dest_account_id", "")),
    }


def _repeats_context(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    *,
    values: Mapping[str, str],
    rows: Sequence[Mapping[str, object]],
    errors: Mapping[str, str] | None,
    formula: tuple[str, str] | None = None,
) -> dict[str, object]:
    """The new-entry context of the repeats tab for ``values`` (the edit dialog's base)."""
    return entry_forms.new_entry_context(
        conn,
        user_id,
        tab="repeats",
        today=today_for(request),
        base_currency=request.app.state.settings.base_currency,
        posted=values,
        terms=rows,
        errors=errors,
        formula=formula,
    )


def _term_rows(
    rule: RecurringRule, terms: Sequence[Mapping[str, object]] | None
) -> Sequence[Mapping[str, object]]:
    """The formula rows to show: the posted ones, else the stored formula's, else one empty."""
    if terms is not None:
        return terms
    if rule.amount_formula is not None:
        return formula_svc.term_input_rows(rule.amount_formula)
    return [dict(EMPTY_TERM_INPUT)]


def _signed_hero(context: dict[str, object]) -> dict[str, object]:
    """Sign the static formula hero (the handoff does) and move its note into the formula body.

    The handoff shows "-> next amount ..." under "+ add component", not in the hero band; the
    note's amount becomes ``next_amount`` of the formula fragment.
    """
    hero = context["hero"]
    if not isinstance(hero, dict):
        return context
    note = str(hero.get("note") or "")
    shown = {k: v for k, v in hero.items() if k != "note"}
    prefix = "\N{RIGHTWARDS ARROW} next amount "
    next_amount = note.removeprefix(prefix) if note.startswith(prefix) else None
    return {
        **context,
        "hero": {"sign": context["sign"], **shown},
        "next_amount": next_amount,
    }


def render_edit_dialog(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    rule_id: int,
    fx: FormulaFx,
    *,
    hero_only: bool = False,
) -> Response:
    """The edit-recurring dialog for the stored rule; ``hero_only`` renders it from the form."""
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="rule: not found")
    if hero_only:
        form = request.query_params
        context = edit_context(
            request,
            conn,
            user_id,
            rule,
            fx,
            posted=dict(form),
            terms=parse_terms_from_form(form) or [dict(EMPTY_TERM_INPUT)],
        )
        return render_context(request, EDIT_TEMPLATE, context)
    return dialog_response(request, EDIT_TEMPLATE, edit_context(request, conn, user_id, rule, fx))


def render_edit_errors(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
    fx: FormulaFx,
    *,
    fields: RuleFields,
    errors: Mapping[str, str],
) -> Response:
    """422: the edit dialog again with the posted values, the summary and the field errors."""
    posted = {
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
    }
    context = edit_context(
        request, conn, user_id, rule, fx, posted=posted, terms=fields.form_terms, errors=errors
    )
    return invalid_dialog_response(request, EDIT_TEMPLATE, context, errors)


def render_formula_result(
    request: Request, result: formula_svc.PreviewResult, currency: str
) -> Response:
    """The live preview text of the formula (``.rd-formula__result``): next amount or the reason."""
    ok = isinstance(result, formula_svc.PreviewOk)
    return render(
        request,
        FORMULA_RESULT_TEMPLATE,
        result=result,
        next_amount=format_money(result.amount_minor, currency)
        if isinstance(result, formula_svc.PreviewOk)
        else "",
        is_ok=ok,
        status_code=200 if ok else 422,
    )


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


def _month_link(rule_id: int, year: int, month: int, delta: int) -> str:
    """Dialog URL of the month ``delta`` months from ``(year, month)`` (the stepper's links)."""
    shifted_year, shifted_month = shift_month(year, month, delta)
    first = date(shifted_year, shifted_month, 1).isoformat()
    return f"{CREATE_ACTION}/{rule_id}/overrides/new?occurrence_date={first}"


def _override_for(
    conn: sqlite3.Connection, user_id: int, rule: RecurringRule, occurrence: date | None
) -> RecurringOverride | None:
    """The stored override of ``occurrence`` (``None`` when there is none or no occurrence)."""
    if occurrence is None:
        return None
    return override_on_next_due(conn, user_id, rule.id, occurrence)


def occurrence_context(
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
    fx: FormulaFx,
    *,
    year: int,
    month: int,
    base_currency: str,
    amount: str | None = None,
    error: OverrideError | None = None,
) -> dict[str, object]:
    """What ``fragments/dialogs/override-occurrence.html`` renders for one month of a rule.

    The amount opens on the stored override of that month's occurrence, else on what the rule
    posts there; ``amount`` (posted text) wins when the dialog comes back with an error.
    """
    account = accounts_service.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    occurrence = recurring_svc.occurrence_in_month(rule, year, month)
    stored = _override_for(conn, user_id, rule, occurrence)
    shown = promote_context(
        conn,
        user_id,
        action="",
        category_id=rule.category_id,
        account=account,
        amount_minor=_override_minor(
            conn, user_id, rule, stored, occurrence or date(year, month, 1), fx=fx
        ),
        date_value=occurrence or date(year, month, 1),
        note_value="",
        base_currency=base_currency,
    )
    category = categories_service.find_by_id(conn, user_id, rule.category_id, include_deleted=True)
    return {
        "title": f"override occurrence \N{MIDDLE DOT} {category.name if category else ''}",
        "action": f"{CREATE_ACTION}/{rule.id}/overrides",
        "hero": _occurrence_hero(shown, amount, error),
        "year": year,
        "month": month,
        "month_label": f"{month_name(month)} {year}",
        "prev_url": _month_link(rule.id, year, month, -1),
        "next_url": _month_link(rule.id, year, month, 1),
        "errors": {error.field: error.message} if error is not None else {},
        "has_override": stored is not None,
    }


def _occurrence_hero(
    shown: Mapping[str, object], amount: str | None, error: OverrideError | None
) -> dict[str, object]:
    """The dialog hero: the stored or rule amount, or the posted text when it comes back."""
    return {
        "currency": shown["currency"],
        "sign": shown["sign"],
        "amount_id": "field-amount",
        "amount_value": shown["amount_value"] if amount is None else amount,
        "error": error.message if error is not None and error.field == "amount" else None,
    }


def _override_minor(
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
    stored: RecurringOverride | None,
    on: date,
    *,
    fx: FormulaFx,
) -> int:
    """The stored override amount of the occurrence, else what the rule posts there."""
    if stored is not None and stored.amount_override is not None:
        return stored.amount_override
    return live_amount(conn, user_id, rule, on, fx)


def render_override_dialog(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    rule_id: int,
    fx: FormulaFx,
    *,
    occurrence: date | None,
    remove: bool = False,
) -> Response:
    """The override dialog of the occurrence's month (default: the next) or its remove confirm."""
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    target = occurrence or rule.next_due
    base = request.app.state.settings.base_currency
    if remove:
        return _remove_confirm(request, conn, user_id, rule, fx=fx, target=target)
    context = occurrence_context(
        conn, user_id, rule, fx, year=target.year, month=target.month, base_currency=base
    )
    return dialog_response(request, OCCURRENCE_TEMPLATE, context)


def _remove_confirm(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
    *,
    fx: FormulaFx,
    target: date,
) -> Response:
    """Confirm dialog for dropping the override stored on ``target``'s occurrence."""
    occurrence = recurring_svc.occurrence_in_month(rule, target.year, target.month)
    stored = _override_for(conn, user_id, rule, occurrence)
    if occurrence is None or stored is None:
        return Response(status_code=404, content="override: not found")
    account = accounts_service.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    category = categories_service.find_by_id(conn, user_id, rule.category_id, include_deleted=True)
    currency = account.currency if account else request.app.state.settings.base_currency
    back_to = format_money(live_amount(conn, user_id, rule, occurrence, fx), currency)
    name = category.name if category else ""
    return dialog_response(
        request,
        OCCURRENCE_REMOVE_TEMPLATE,
        {
            "action": f"{CREATE_ACTION}/{rule.id}/overrides/{occurrence.isoformat()}/delete",
            "text": f"{name} \N{MIDDLE DOT} {month_name(occurrence.month)} {occurrence.year} "
            f"goes back to the rule amount {back_to}.",
        },
    )


def render_override_error(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    rule: RecurringRule,
    fx: FormulaFx,
    *,
    year: int,
    month: int,
    amount: str,
    error: OverrideError,
) -> Response:
    """422: the override dialog again with the posted amount, the summary and the error."""
    shown_year = year if year in range(1900, 10000) else rule.next_due.year
    shown_month = month if month in range(1, 13) else rule.next_due.month
    context = occurrence_context(
        conn,
        user_id,
        rule,
        fx,
        year=shown_year,
        month=shown_month,
        base_currency=request.app.state.settings.base_currency,
        amount=amount,
        error=error,
    )
    return invalid_dialog_response(
        request, OCCURRENCE_TEMPLATE, context, {error.field: error.message}
    )
