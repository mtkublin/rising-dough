"""Override dialog submissions (T-UR11b, ADR-0107 section 3): save and remove responses.

The router parses nothing beyond the form fields; this module validates them, calls the budget
services (one repository write each, row and audit atomic) and answers with the dialog shapes of
``web.dialogs``: success closes the dialog and sends ``budget-stale``, failure is a 422 that
re-renders the dialog with the summary and writes nothing.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import HTMLResponse, Response

from budget_planner.services import budget_rules
from budget_planner.web import override_forms, plan_data, plan_year_view
from budget_planner.web.budget_forms import parse_override
from budget_planner.web.dialogs import invalid_dialog_response, saved_response
from budget_planner.web.htmx import Event
from budget_planner.web.rendering import is_hx_request, render

DIALOG_TEMPLATE = "fragments/dialogs/override-budget.html"
REMOVE_TEMPLATE = "fragments/dialogs/override-remove.html"
PAGE_TEMPLATE = "pages/plan/override-page.html"


def in_page(request: Request, response: HTMLResponse) -> HTMLResponse:
    """A dialog response as is over HTMX; on a plain request the same dialog inside the app shell.

    Status and HX headers carry over (the plan contract pins them on the dialog route).
    """
    if is_hx_request(request):
        return response
    page = render(
        request,
        PAGE_TEMPLATE,
        response.status_code,
        dialog_html=bytes(response.body).decode(),
        nav_current="plan",
    )
    for name, value in response.headers.items():
        if name.lower().startswith("hx-"):
            page.headers[name] = value
    return page


@dataclass(frozen=True, slots=True)
class OverrideForm:
    """The dialog form as submitted, with the currency amounts are read in."""

    tier: str
    month: str
    year: str
    amount: str
    currency: str
    origin: str = ""  # ``override_forms.YEAR_ORIGIN`` from the year grid's inline editor


def save(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    shown: plan_year_view.OverrideTarget,
    form: OverrideForm,
) -> Response:
    """Store the default, recurring or one-off amount, or answer 422 with the dialog again."""
    from_year = form.origin == override_forms.YEAR_ORIGIN
    parsed = parse_override(
        shown.category_id,
        allow_default=not from_year,
        tier=form.tier,
        month=form.month,
        year=form.year,
        amount=form.amount,
        currency=form.currency,
    )
    if parsed.command is None:
        field, message = override_forms.rejection(parsed.error)
        tier = plan_year_view.TIER_ONE_OFF if from_year else override_forms.scope(form.tier)
        dialog = plan_data.override_dialog_for(
            conn,
            user_id,
            shown,
            tier=tier,
            currency=form.currency,
            amount_text=form.amount,
            error=message if field == "amount" else None,
        )
        return in_page(
            request,
            invalid_dialog_response(
                request, DIALOG_TEMPLATE, {"override": dialog}, {field: message}
            ),
        )
    budget_rules.apply_override(conn, user_id, parsed.command)
    return saved_response(
        request,
        None,
        {},
        message=f"{shown.category_name} budget saved",
        events=(Event.BUDGET_STALE,),
    )


def remove(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    shown: plan_year_view.OverrideTarget,
    form: OverrideForm,
) -> Response:
    """Soft-delete the one-off or recurring override the confirm named, or answer 422."""
    removal = override_forms.parse_removal(form.tier, form.month, form.year)
    if removal.errors or removal.month is None:
        confirm = plan_data.remove_confirm_for(
            conn, user_id, shown, tier=override_forms.scope(form.tier), currency=form.currency
        )
        return in_page(
            request,
            invalid_dialog_response(request, REMOVE_TEMPLATE, {"confirm": confirm}, removal.errors),
        )
    budget_rules.remove_override(
        conn, user_id, shown.category_id, month=removal.month, year=removal.year
    )
    return saved_response(
        request,
        None,
        {},
        message=f"{shown.category_name} override removed",
        events=(Event.BUDGET_STALE,),
    )
