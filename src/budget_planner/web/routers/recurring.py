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
from budget_planner.web.dialogs import saved_response
from budget_planner.web.htmx import Event, refresh_unless_on
from budget_planner.web.params import parse_date, parse_int, query_date
from budget_planner.web.paths import LEDGER_PATH, NEW_PATH
from budget_planner.web.view_models import month_name

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
    posting_category_id = parse_int(
        forms.category_alias(str(form.get("category_id", "")), str(form.get("category", "")))
    )
    result = formula_svc.preview(
        conn,
        user_id,
        today_for(request),
        draft_rule_id,
        drafts,
        fx=fx,
        target_ccy=target_ccy,
        posting_category_id=posting_category_id,
    )
    return views.render_formula_result(request, result, target_ccy)


@router.get("/{rule_id}/edit", response_class=HTMLResponse)
def edit_form(
    rule_id: int,
    request: Request,
    *,
    hero: str = "",
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
    fx: FormulaFx = Depends(get_formula_fx),
) -> Response:
    """The edit-recurring dialog (T-UR10); ``hero=1`` renders it from the form for the hero swap."""
    return views.render_edit_dialog(request, conn, user_id, rule_id, fx, hero_only=bool(hero))


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
    draft = forms.validate_rule_draft(
        conn,
        user_id,
        fields,
        forms.parse_rule_ids(fields),
        fx=fx,
        today=today_for(request),
        exclude_rule_id=rule_id,
        cadence_error="invalid",
    )
    if draft.valid is None:
        return views.render_edit_errors(
            request, conn, user_id, rule, fx, fields=fields, errors=draft.errors
        )
    recurring_svc.update_rule(
        conn, user_id, rule_id, forms.rule_patch_from(fields, draft.valid, rule)
    )
    return saved_response(
        request,
        None,
        {},
        message="Recurring rule saved",
        events=(Event.FORECAST_STALE, Event.LEDGER_STALE),
    )


@router.post("/{rule_id}/deactivate")
def deactivate_rule(
    rule_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    recurring_svc.deactivate_rule(conn, user_id, rule_id)
    # The menu item posts with swap "none": the ledger-stale event refetches the table, the flash
    # confirms. removed_response would delete the menu button, so it is not used here.
    return saved_response(
        request,
        None,
        {},
        message="Recurring rule deactivated",
        events=(Event.LEDGER_STALE, Event.FORECAST_STALE),
    )


@router.get("/{rule_id}/overrides/new", response_class=HTMLResponse)
def new_override_form(
    rule_id: int,
    request: Request,
    *,
    occurrence_date: str = "",
    remove: str = "",
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
    fx: FormulaFx = Depends(get_formula_fx),
) -> Response:
    """Override dialog of the occurrence's month (default: the next), or its remove confirm."""
    return views.render_override_dialog(
        request,
        conn,
        user_id,
        rule_id,
        fx,
        occurrence=query_date("occurrence_date", occurrence_date),
        remove=remove == "1",
    )


@router.post("/{rule_id}/overrides")
def add_override(
    rule_id: int,
    request: Request,
    *,
    year: str = Form(""),
    month: str = Form(""),
    amount: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
    fx: FormulaFx = Depends(get_formula_fx),
) -> Response:
    rule = recurring_svc.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    acc = accounts_service.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    shown_year, shown_month = parse_int(year) or 0, parse_int(month) or 0
    checked = forms.check_override(rule, acc, shown_year, shown_month, amount)
    if isinstance(checked, forms.OverrideError):
        return views.render_override_error(
            request,
            conn,
            user_id,
            rule,
            fx,
            year=shown_year,
            month=shown_month,
            amount=amount,
            error=checked,
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
    return saved_response(
        request,
        None,
        {},
        message=f"Override saved \N{MIDDLE DOT} {month_name(checked.occurrence.month)}",
        events=(Event.FORECAST_STALE, Event.LEDGER_STALE),
    )


@router.post("/{rule_id}/overrides/{occurrence_date}/delete")
def delete_override(
    rule_id: int,
    occurrence_date: str,
    request: Request,
    *,
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
    return saved_response(
        request,
        None,
        {},
        message="Override removed",
        events=(Event.FORECAST_STALE, Event.LEDGER_STALE),
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
        errors = {"promotion": str(exc)}
        return views.render_promote_modal(
            request, conn, user_id, rule_id, fx, errors=errors, posted=posted
        )
    response = saved_response(
        request,
        None,
        {},
        message="Recurring occurrence promoted",
        events=(Event.LEDGER_STALE, Event.FORECAST_STALE, Event.BUDGET_STALE),
    )
    refresh_unless_on(request, response, LEDGER_PATH)
    return response


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
    return saved_response(
        request,
        None,
        {},
        message="Next occurrence skipped",
        events=(Event.LEDGER_STALE, Event.FORECAST_STALE, Event.BUDGET_STALE),
    )
