"""Recurring rules router (T-035; formula support per ADR-0047)."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget_planner.domain.enums import OverrideState
from budget_planner.domain.recurring import (
    NewRecurringOverride,
)
from budget_planner.services import (
    accounts as accounts_service,
    recurring as recurring_svc,
    recurring_formula as formula_svc,
)
from budget_planner.services._promotion import UnsupportedDirectionError, ValidationError
from budget_planner.services.recurring_formula import FormulaFx
from budget_planner.web import recurring_forms as forms, recurring_views as views
from budget_planner.web.deps import current_user_id, get_db, get_formula_fx, today_for
from budget_planner.web.htmx import Event, trigger
from budget_planner.web.http_headers import HTML_MEDIA_TYPE
from budget_planner.web.params import parse_date, parse_int, query_date
from budget_planner.web.paths import NEW_PATH
from budget_planner.web.rendering import render

router = APIRouter(prefix="/recurring", tags=["recurring"])


@router.get(NEW_PATH, response_class=HTMLResponse)
def new_form(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    return views.render_new_form(request, conn, user_id)


@router.post("")
async def create_rule(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
    fx: FormulaFx = Depends(get_formula_fx),
) -> Response:
    fields = forms.read_rule_fields(await request.form())
    today = today_for(request)
    draft = forms.validate_rule_draft(
        conn,
        user_id,
        fields,
        forms.parse_rule_ids(fields),
        fx=fx,
        today=today,
        exclude_rule_id=None,
        cadence_error="invalid cadence",
    )
    if draft.valid is None:
        return views.render_rule_form_errors(
            request,
            conn,
            user_id,
            rule=None,
            action=views.CREATE_ACTION,
            fields=fields,
            errors=draft.errors,
        )
    valid = draft.valid
    rule = recurring_svc.create_rule(conn, user_id, forms.new_rule_from(fields, valid, today))
    return views.render_created_row(
        request, rule, valid.account, valid.category, valid.amount_minor
    )


# ADR-0056 §4 live formula preview. Registered BEFORE `/{rule_id}` so FastAPI's
# int-path validator does not swallow the literal `formula` segment.
@router.post("/formula/preview", response_class=HTMLResponse)
async def formula_preview(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
    fx: FormulaFx = Depends(get_formula_fx),
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
    target_ccy = views.preview_currency(conn, user_id, form.get("account_id"), draft_rule_id, fx)
    result = formula_svc.preview(
        conn, user_id, today_for(request), draft_rule_id, drafts, fx=fx, target_ccy=target_ccy
    )
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
    return views.render_edit_form(request, conn, user_id, rule_id)


@router.post("/{rule_id}")
async def update_rule_handler(
    rule_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
    fx: FormulaFx = Depends(get_formula_fx),
) -> Response:
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    fields = forms.read_rule_fields(await request.form())
    ids = forms.parse_rule_ids(fields)
    if ids is None:
        return Response(status_code=422, content="invalid account/category")
    draft = forms.validate_rule_draft(
        conn,
        user_id,
        fields,
        ids,
        fx=fx,
        today=today_for(request),
        exclude_rule_id=rule_id,
        cadence_error="invalid",
    )
    if draft.valid is None:
        return views.render_rule_form_errors(
            request,
            conn,
            user_id,
            rule=rule,
            action=f"/recurring/{rule_id}",
            fields=fields,
            errors=draft.errors,
        )
    recurring_svc.update_rule(
        conn, user_id, rule_id, forms.rule_patch_from(fields, draft.valid, rule)
    )
    # Hosted by every page (T-D151): no row swap; refetch on the ledger, reload elsewhere.
    return views.stale_response(request, Event.FORECAST_STALE, Event.LEDGER_STALE)


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
    resp = Response(content="", media_type=HTML_MEDIA_TYPE)
    trigger(resp, Event.LEDGER_STALE, Event.FORECAST_STALE)
    return resp


@router.get("/{rule_id}/overrides/new", response_class=HTMLResponse)
def new_override_form(
    rule_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    return views.render_override_form(request, conn, user_id, rule_id)


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
    checked = forms.check_override(rule, acc, year, month, amount)
    if isinstance(checked, forms.OverrideError):
        return views.render_override_error(
            request, rule, acc, year=year, month=month, amount=amount, error=checked
        )
    recurring_svc.upsert_override(
        conn,
        user_id,
        NewRecurringOverride(
            rule_id=rule_id,
            occurrence_date=checked.occurrence,
            state=OverrideState.OVERRIDDEN,
            amount_override=checked.amount_minor,
            description_override=None,
            date_override=None,
        ),
    )
    return views.stale_response(request, Event.FORECAST_STALE, Event.LEDGER_STALE)


@router.post("/{rule_id}/overrides/{occurrence_date}/delete")
def delete_override(
    rule_id: int,
    occurrence_date: str,
    request: Request,
    *,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
    fx: FormulaFx = Depends(get_formula_fx),
) -> Response:
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    occ = parse_date(occurrence_date)
    if occ is None:
        return Response(status_code=422, content="invalid date")
    recurring_svc.delete_override(conn, user_id, rule_id, occ)
    return views.render_rule_row(
        request, conn, user_id, rule, fx, Event.FORECAST_STALE, Event.LEDGER_STALE
    )


# ---------------------------------------------------------------------------
# T-118 — Promote / Skip-next (ADR-0038)
# ---------------------------------------------------------------------------


@router.get("/{rule_id}/promote", response_class=HTMLResponse)
def promote_form(
    rule_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
    fx: FormulaFx = Depends(get_formula_fx),
) -> Response:
    return views.render_promote_modal(request, conn, user_id, rule_id, fx)


@router.get("/{rule_id}/promote/inline", response_class=HTMLResponse)
def promote_inline(
    rule_id: int,
    request: Request,
    date: str = "",
    *,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
    fx: FormulaFx = Depends(get_formula_fx),
) -> Response:
    """F-02 — Row-expand inline form for Today Upcoming Promote action.

    Returns a <tr> fragment that replaces the current upcoming row, letting
    the user edit `date` + `amount` and Confirm without leaving the page.
    """
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    occurrence = query_date("date", date) or rule.next_due
    return views.render_inline_promote_row(
        request, conn, user_id, rule, occurrence=occurrence, fx=fx
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
    fx: FormulaFx = Depends(get_formula_fx),
) -> Response:
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    account = accounts_service.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    parsed = forms.parse_promote_input(operation_date, amount, account)
    posted = {"amount": amount, "operation_date": operation_date, "description": description}
    if parsed.errors:
        return views.render_promote_modal(
            request, conn, user_id, rule_id, fx, errors=parsed.errors, posted=posted
        )
    edits = recurring_svc.PromotionEdits(
        operation_date=parsed.operation_date,
        amount_minor=parsed.amount_minor,
        description=description or None,
    )
    try:
        recurring_svc.promote_recurring(conn, user_id, rule_id, edits, fx=fx)
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
            fx,
            errors={"promotion": str(exc)},
            posted=posted,
        )
    return views.stale_response(
        request, Event.LEDGER_STALE, Event.FORECAST_STALE, Event.BUDGET_STALE
    )


@router.post("/{rule_id}/skip-next")
def skip_next(
    rule_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
    fx: FormulaFx = Depends(get_formula_fx),
) -> Response:
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    try:
        recurring_svc.skip_and_advance(conn, user_id, rule_id)
    except recurring_svc.InactiveRecurringError:
        return Response(status_code=422, content="rule is inactive")
    updated = recurring_svc.find_rule(conn, user_id, rule_id, include_deleted=True)
    if updated is None:
        return Response(status_code=404, content="not found")
    return views.render_rule_row(
        request,
        conn,
        user_id,
        updated,
        fx,
        Event.LEDGER_STALE,
        Event.FORECAST_STALE,
        Event.BUDGET_STALE,
    )
