"""Recurring rules router (T-035; formula support per ADR-0047)."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget_planner.domain.enums import OverrideState
from budget_planner.domain.money import format_major
from budget_planner.domain.recurring import (
    NewRecurringOverride,
    NewRecurringRule,
    PatchRecurringRule,
)
from budget_planner.services import (
    accounts as accounts_service,
    categories as categories_service,
    recurring as recurring_svc,
    recurring_formula as formula_svc,
)
from budget_planner.services._promotion import UnsupportedDirectionError, ValidationError
from budget_planner.web import recurring_forms as forms, recurring_views as views
from budget_planner.web.deps import current_user_id, get_db, today_for
from budget_planner.web.htmx import Event, refresh_unless_on, trigger
from budget_planner.web.params import parse_date, parse_int, positive_amount
from budget_planner.web.rendering import render

router = APIRouter(prefix="/recurring", tags=["recurring"])


@router.get("/new", response_class=HTMLResponse)
def new_form(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    # T-069 — slide-over wrapper for FAB launches.
    return render(
        request,
        "partials/_slideover.html",
        slide_over_title="New recurring rule",
        form_include="partials/recurring/_form.html",
        rule=None,
        action="/recurring",
        categories=categories_service.list_all(conn, user_id),
        accounts=accounts_service.list_all(conn, user_id),
        source_categories=forms.formula_source_candidates(conn, user_id),
        amount_source="fixed",
        terms=[dict(forms.EMPTY_TERM_INPUT)],
        errors={},
    )


@router.post("")
async def create_rule(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    form = await request.form()
    cadence = str(form.get("cadence", ""))
    start_date = str(form.get("start_date", ""))
    end_date_raw = str(form.get("end_date", ""))
    category_id_raw = str(form.get("category_id", ""))
    account_id_raw = str(form.get("account_id", ""))
    dest_account_id_raw = str(form.get("dest_account_id", ""))
    default_amount = str(form.get("default_amount", ""))
    default_description = str(form.get("default_description", ""))
    day_of_month = str(form.get("day_of_month", ""))
    amount_source = str(form.get("amount_source", "fixed"))
    term_inputs = forms.parse_terms_from_form(form)

    errors: dict[str, str] = {}
    c = forms.validate_cadence(cadence)
    if c is None:
        errors["cadence"] = "invalid cadence"
    start = parse_date(start_date)
    if start is None:
        errors["start_date"] = "invalid date"
    end: date | None = None
    if end_date_raw:
        end = parse_date(end_date_raw)
        if end is None:
            errors["end_date"] = "invalid date"
        elif start is not None and end < start:
            errors["end_date"] = "must be on or after start"
    try:
        category_id = int(category_id_raw)
        account_id = int(account_id_raw)
    except ValueError:
        errors["account_id"] = "invalid account/category"
        return views.render_form_errors(
            request,
            conn,
            user_id,
            rule=None,
            action="/recurring",
            errors=errors,
            amount_source=amount_source,
            terms=term_inputs or [dict(forms.EMPTY_TERM_INPUT)],
        )
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    cat = categories_service.find_by_id(conn, user_id, category_id)
    if acc is None:
        errors["account_id"] = "unknown account"
    if cat is None:
        errors["category_id"] = "unknown category"
    dest_id, dest_errors = forms.resolve_dest_account(
        conn,
        user_id,
        dest_account_id_raw=dest_account_id_raw,
        category=cat,
        source_account=acc,
    )
    errors.update(dest_errors)
    minor, formula, amount_errors = forms.resolve_amount_inputs(
        conn,
        user_id,
        amount_source=amount_source,
        default_amount=default_amount,
        term_inputs=term_inputs,
        account_currency=acc.currency if acc else None,
        exclude_rule_id=None,
        today=today_for(request),
    )
    errors.update(amount_errors)
    if errors:
        return views.render_form_errors(
            request,
            conn,
            user_id,
            rule=None,
            action="/recurring",
            errors=errors,
            amount_source=amount_source,
            terms=term_inputs or [dict(forms.EMPTY_TERM_INPUT)],
        )
    assert c is not None and start is not None and minor is not None
    today = today_for(request)
    # ADR-0063: a stop date already in the past means the schedule is dead
    # on arrival — insert as inactive so it never shows up in Upcoming
    # or Forecast between create and the first promotion attempt.
    initial_active = not (end is not None and end < today)
    rule = recurring_svc.create_rule(
        conn,
        user_id,
        recurring_svc.with_anchor_day(
            NewRecurringRule(
                cadence=c,
                start_date=start,
                end_date=end,
                category_id=category_id,
                account_id=account_id,
                dest_account_id=dest_id,
                default_amount=minor,
                default_description=default_description,
                day_of_month=parse_int(day_of_month),
                amount_formula=formula,
                active=initial_active,
            )
        ),
    )
    html = render(
        request,
        "partials/recurring/_row.html",
        rule=rule,
        overrides=[],
        account=acc,
        category=cat,
        effective_amount_minor=minor,
    )
    trigger(html, Event.FORECAST_STALE, Event.LEDGER_STALE)
    # See create_planned: no row insert; refetch on the ledger, reload elsewhere.
    refresh_unless_on(request, html, "/ledger")
    return html


# ADR-0056 §4 live formula preview. Registered BEFORE `/{rule_id}` so FastAPI's
# int-path validator does not swallow the literal `formula` segment.
@router.post("/formula/preview", response_class=HTMLResponse)
async def formula_preview(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    """Live-preview chip or inline error for a draft formula (no DB write)."""
    form = await request.form()
    draft_rule_id_raw = str(form.get("draft_rule_id", ""))
    draft_rule_id = parse_int(draft_rule_id_raw)
    if draft_rule_id_raw and draft_rule_id is None:
        return Response(status_code=422, content="invalid draft_rule_id")
    drafts = forms.parse_draft_terms(form)
    if drafts is None:
        return Response(status_code=422, content="invalid source_category_ids")
    result = formula_svc.preview(conn, user_id, today_for(request), draft_rule_id, drafts)
    is_ok = isinstance(result, formula_svc.PreviewOk)
    return render(
        request,
        "partials/recurring/_formula_preview.html",
        result=result,
        is_ok=is_ok,
        status_code=200 if is_ok else 422,
    )


@router.get("/{rule_id}/edit", response_class=HTMLResponse)
def edit_form(
    rule_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return render(
            request,
            "partials/recurring/_form.html",
            rule=None,
            action="",
            categories=[],
            accounts=[],
            source_categories=[],
            amount_source="fixed",
            terms=[dict(forms.EMPTY_TERM_INPUT)],
            errors={"rule": "not found"},
            status_code=404,
        )
    amount_source, terms = (
        ("fixed", [dict(forms.EMPTY_TERM_INPUT)])
        if rule is None or rule.amount_formula is None
        else ("formula", formula_svc.term_input_rows(rule.amount_formula))
    )
    # T-114 / ADR-0030 §4 — slide-over wrapper mirrors /recurring/new.
    return render(
        request,
        "partials/_slideover.html",
        slide_over_title="Edit recurring rule",
        form_include="partials/recurring/_form.html",
        rule=rule,
        action=f"/recurring/{rule_id}",
        categories=categories_service.list_all(conn, user_id),
        accounts=accounts_service.list_all(conn, user_id),
        source_categories=forms.formula_source_candidates(conn, user_id),
        amount_source=amount_source,
        terms=terms,
        errors={},
    )


@router.post("/{rule_id}")
async def update_rule_handler(  # noqa: PLR0915 — flat validation surface
    rule_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    form = await request.form()
    cadence = str(form.get("cadence", ""))
    start_date = str(form.get("start_date", ""))
    end_date_raw = str(form.get("end_date", ""))
    category_id_raw = str(form.get("category_id", ""))
    account_id_raw = str(form.get("account_id", ""))
    dest_account_id_raw = str(form.get("dest_account_id", ""))
    default_amount = str(form.get("default_amount", ""))
    default_description = str(form.get("default_description", ""))
    amount_source = str(form.get("amount_source", "fixed"))
    term_inputs = forms.parse_terms_from_form(form)
    try:
        category_id = int(category_id_raw)
        account_id = int(account_id_raw)
    except ValueError:
        return Response(status_code=422, content="invalid account/category")
    acc = accounts_service.find_by_id(conn, user_id, account_id)
    cat = categories_service.find_by_id(conn, user_id, category_id)
    c = forms.validate_cadence(cadence)
    start = parse_date(start_date)
    end: date | None = None
    errors: dict[str, str] = {}
    if c is None:
        errors["cadence"] = "invalid"
    if start is None:
        errors["start_date"] = "invalid date"
    if end_date_raw:
        end = parse_date(end_date_raw)
        if end is None:
            errors["end_date"] = "invalid date"
        elif start is not None and end < start:
            errors["end_date"] = "must be on or after start"
    if acc is None:
        errors["account_id"] = "unknown account"
    if cat is None:
        errors["category_id"] = "unknown category"
    dest_id, dest_errors = forms.resolve_dest_account(
        conn,
        user_id,
        dest_account_id_raw=dest_account_id_raw,
        category=cat,
        source_account=acc,
    )
    errors.update(dest_errors)
    minor, formula, amount_errors = forms.resolve_amount_inputs(
        conn,
        user_id,
        amount_source=amount_source,
        default_amount=default_amount,
        term_inputs=term_inputs,
        account_currency=acc.currency if acc else None,
        exclude_rule_id=rule_id,
        today=today_for(request),
    )
    errors.update(amount_errors)
    if errors:
        return views.render_form_errors(
            request,
            conn,
            user_id,
            rule=rule,
            action=f"/recurring/{rule_id}",
            errors=errors,
            amount_source=amount_source,
            terms=term_inputs or [dict(forms.EMPTY_TERM_INPUT)],
        )
    assert c is not None and start is not None and minor is not None
    # ADR-0063: if the user shortens the stop date so that the next pending
    # occurrence falls past it, deactivate the rule in the same patch so
    # Upcoming + Forecast stop surfacing it before the next promotion.
    end_is_set = bool(end_date_raw)
    deactivate_due_to_end = end_is_set and end is not None and rule.next_due > end
    patch_kwargs: dict[str, Any] = {
        "cadence": c,
        "start_date": start,
        "category_id": category_id,
        "account_id": account_id,
        "dest_account_id": dest_id,
        "default_amount": minor,
        "default_description": default_description,
        "amount_formula": formula,
    }
    # end_date is sentinel-nullable; only touch it when the form carried a
    # value (empty string clears, missing field leaves as-is — forms always
    # include it, so we treat empty as explicit clear).
    patch_kwargs["end_date"] = end
    if deactivate_due_to_end:
        patch_kwargs["active"] = False
    recurring_svc.update_rule(
        conn,
        user_id,
        rule_id,
        PatchRecurringRule(**patch_kwargs),
    )
    # Hosted by every page (T-D151): no row swap; refetch on the ledger, reload elsewhere.
    html = Response()
    trigger(html, Event.FORECAST_STALE, Event.LEDGER_STALE)
    refresh_unless_on(request, html, "/ledger")
    return html


@router.post("/{rule_id}/deactivate")
def deactivate_rule(
    rule_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    recurring_svc.deactivate_rule(conn, user_id, rule_id)
    # Empty body + ledger-stale trigger removes the row from the Ledger
    # Recurring tab (hx-swap="outerHTML") and re-fetches the table so
    # inactive rules disappear from view. Mirrors transactions/delete.
    resp = Response(content="", media_type="text/html")
    trigger(resp, Event.LEDGER_STALE, Event.FORECAST_STALE)
    return resp


@router.get("/{rule_id}/overrides/new", response_class=HTMLResponse)
def new_override_form(
    rule_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    """Generic override form. Picks (year, month, amount); server resolves
    the exact ``occurrence_date`` on submit via
    ``services.recurring.occurrence_in_month``. Defaults year + month to the
    rule's current ``next_due``.
    """
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return render(
            request,
            "partials/recurring/_override_form.html",
            rule=None,
            account=None,
            default_year=None,
            default_month=None,
            default_amount_str=None,
            errors={"rule": "not found"},
            status_code=404,
        )
    account = accounts_service.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    default_amount_str = format_major(rule.default_amount, account.currency) if account else ""
    return render(
        request,
        "partials/recurring/_override_form.html",
        rule=rule,
        account=account,
        default_year=rule.next_due.year,
        default_month=rule.next_due.month,
        default_amount_str=default_amount_str,
        errors={},
    )


@router.post("/{rule_id}/overrides")
def add_override(
    rule_id: int,
    request: Request,
    *,
    year: int = Form(...),
    month: int = Form(...),
    amount: str = Form(...),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    acc = accounts_service.find_by_id(conn, user_id, rule.account_id, include_deleted=True)

    def _invalid(field: str, message: str) -> Response:
        # T-D151: re-render the override form with the error inside the slide-over.
        return render(
            request,
            "partials/recurring/_override_form.html",
            rule=rule,
            account=acc,
            default_year=year if 1900 <= year <= 9999 else rule.next_due.year,  # noqa: PLR2004
            default_month=month if 1 <= month <= 12 else rule.next_due.month,  # noqa: PLR2004
            default_amount_str=amount,
            errors={field: message},
            status_code=422,
        )

    if not (1900 <= year <= 9999 and 1 <= month <= 12):  # noqa: PLR2004
        return _invalid("month", "invalid year or month")
    occ = recurring_svc.occurrence_in_month(rule, year, month)
    if occ is None:
        return _invalid("month", f"rule has no occurrence in {year:04d}-{month:02d}")
    if acc is None:
        return _invalid("account", "rule has no live account")
    amount_minor, amount_err = positive_amount(amount, acc.currency)
    if amount_minor is None:
        return _invalid("amount", amount_err or "invalid amount")
    recurring_svc.upsert_override(
        conn,
        user_id,
        NewRecurringOverride(
            rule_id=rule_id,
            occurrence_date=occ,
            state=OverrideState.OVERRIDDEN,
            amount_override=amount_minor,
            description_override=None,
            date_override=None,
        ),
    )
    html = Response()
    trigger(html, Event.FORECAST_STALE, Event.LEDGER_STALE)
    refresh_unless_on(request, html, "/ledger")
    return html


@router.post("/{rule_id}/overrides/{occurrence_date}/delete")
def delete_override(
    rule_id: int,
    occurrence_date: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    occ = parse_date(occurrence_date)
    if occ is None:
        return Response(status_code=422, content="invalid date")
    recurring_svc.delete_override(conn, user_id, rule_id, occ)
    overrides = recurring_svc.list_overrides(conn, user_id, rule_id)
    acc = accounts_service.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    cat = categories_service.find_by_id(conn, user_id, rule.category_id, include_deleted=True)
    html = render(
        request,
        "partials/recurring/_row.html",
        rule=rule,
        effective_amount_minor=views.effective_amount_for_render(conn, user_id, rule),
        overrides=overrides,
        account=acc,
        category=cat,
    )
    trigger(html, Event.FORECAST_STALE, Event.LEDGER_STALE)
    return html


# ---------------------------------------------------------------------------
# T-118 — Promote / Skip-next (ADR-0038)
# ---------------------------------------------------------------------------


@router.get("/{rule_id}/promote", response_class=HTMLResponse)
def promote_form(
    rule_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    return views.render_promote_modal(request, conn, user_id, rule_id)


@router.get("/{rule_id}/promote/inline", response_class=HTMLResponse)
def promote_inline(
    rule_id: int,
    request: Request,
    date: str = "",
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    """F-02 — Row-expand inline form for Today Upcoming Promote action.

    Returns a <tr> fragment that replaces the current upcoming row, letting
    the user edit `date` + `amount` and Confirm without leaving the page.
    """
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    account = accounts_service.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    occurrence = parse_date(date) or rule.next_due
    override = views.override_on_next_due(conn, user_id, rule_id, occurrence)
    prefill_amount = formula_svc.resolve_rule_amount(conn, user_id, rule, occurrence)
    prefill_description = rule.default_description
    if override is not None:
        if override.amount_override is not None:
            prefill_amount = override.amount_override
        if override.description_override is not None:
            prefill_description = override.description_override
    categories_by_id = {c.id: c for c in categories_service.list_all(conn, user_id)}
    return render(
        request,
        "partials/recurring/_promote_inline_row.html",
        rule=rule,
        account=account,
        occurrence_date=occurrence,
        prefill_amount_minor=prefill_amount,
        prefill_description=prefill_description,
        categories_by_id=categories_by_id,
    )


@router.post("/{rule_id}/promote")
def promote_submit(
    rule_id: int,
    request: Request,
    *,
    operation_date: str = Form(""),
    amount: str = Form(""),
    description: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    account = accounts_service.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    errors: dict[str, str] = {}

    op_date: date | None = None
    if operation_date:
        op_date = parse_date(operation_date)
        if op_date is None:
            errors["operation_date"] = "invalid date"

    amount_minor: int | None = None
    if amount:
        if account is None:
            errors["amount"] = "unknown account currency"
        else:
            amount_minor, amount_err = positive_amount(amount, account.currency)
            if amount_err is not None:
                errors["amount"] = amount_err

    if errors:
        return views.render_promote_modal(
            request, conn, user_id, rule_id, errors=errors, status_code=422
        )

    edits = recurring_svc.PromotionEdits(
        operation_date=op_date,
        amount_minor=amount_minor,
        description=description or None,
    )
    try:
        recurring_svc.promote_recurring(conn, user_id, rule_id, edits)
    except recurring_svc.RecurringNotFoundError:
        return Response(status_code=404, content="not found")
    except (
        recurring_svc.InactiveRecurringError,
        recurring_svc.CannotPromoteSkippedError,
        UnsupportedDirectionError,
        ValidationError,
    ) as exc:
        return views.render_promote_modal(
            request,
            conn,
            user_id,
            rule_id,
            errors={"promotion": str(exc)},
            status_code=422,
        )

    html = Response()
    trigger(html, Event.LEDGER_STALE, Event.FORECAST_STALE, Event.BUDGET_STALE)
    refresh_unless_on(request, html, "/ledger")
    return html


@router.post("/{rule_id}/skip-next")
def skip_next(
    rule_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    try:
        recurring_svc.skip_and_advance(conn, user_id, rule_id)
    except recurring_svc.InactiveRecurringError:
        return Response(status_code=422, content="rule is inactive")
    updated = recurring_svc.find_rule(conn, user_id, rule_id, include_deleted=True)
    assert updated is not None
    acc = accounts_service.find_by_id(conn, user_id, updated.account_id, include_deleted=True)
    cat = categories_service.find_by_id(conn, user_id, updated.category_id, include_deleted=True)
    html = render(
        request,
        "partials/recurring/_row.html",
        rule=updated,
        overrides=recurring_svc.list_overrides(conn, user_id, rule_id),
        account=acc,
        category=cat,
        effective_amount_minor=views.effective_amount_for_render(conn, user_id, updated),
    )
    trigger(html, Event.LEDGER_STALE, Event.FORECAST_STALE, Event.BUDGET_STALE)
    return html
