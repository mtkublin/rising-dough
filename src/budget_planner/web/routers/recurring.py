"""Recurring rules router (T-035; formula support per ADR-0047)."""

from __future__ import annotations

import datetime as dt
import re
import sqlite3
from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from starlette.datastructures import FormData

from budget_planner.domain.enums import Cadence, Direction, OverrideState
from budget_planner.domain.money import to_minor_units
from budget_planner.domain.recurring import (
    AmountFormula,
    NewRecurringOverride,
    NewRecurringRule,
    PatchRecurringRule,
    RecurringOverride,
)
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    recurring as recurring_repo,
)
from budget_planner.services import recurring as recurring_svc, recurring_formula as formula_svc
from budget_planner.services._promotion import UnsupportedDirectionError, ValidationError
from budget_planner.web.deps import current_user_id, get_db
from budget_planner.web.htmx import trigger
from budget_planner.web.rendering import render

router = APIRouter(prefix="/recurring", tags=["recurring"])


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _parse_int(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


@router.get("")
def index() -> RedirectResponse:
    """Legacy page URL (T-070).

    Redirects to the unified ledger with the ``recurring`` view selected. The
    CRUD sub-routes (``/recurring/new``, ``/recurring/{id}/edit``, etc.)
    remain live for the FAB and settings tooling.
    """
    return RedirectResponse(url="/ledger?view=recurring", status_code=302)


def _formula_source_candidates(conn: sqlite3.Connection, user_id: int) -> list[Any]:
    """Return categories eligible as formula sources (user-visible income+expense)."""
    return [
        c
        for c in categories_repo.list_all(conn, user_id)
        if c.direction in (Direction.INCOME, Direction.EXPENSE)
    ]


_EMPTY_TERM_INPUT: dict[str, Any] = {
    "sign": "+",
    "coefficient_percent": "",
    "source_category_ids": (),
}

_TERM_FIELD_RE = re.compile(r"^terms\[(\d+)\]\[(sign|coefficient_percent|source_category_ids)\]$")


def _parse_terms_from_form(form: FormData) -> list[dict[str, Any]]:
    """Group `terms[i][field]` form entries into a dense indexed list.

    Returns a list of ``{"sign", "coefficient_percent", "source_category_ids"}``
    dicts in ascending index order. Holes (removed row 1 in a form that
    posted rows 0 and 2) collapse to a contiguous list. Values are left as
    strings / tuples so :func:`formula_svc.build_term` is the single
    validation boundary.
    """
    by_index: dict[int, dict[str, Any]] = {}
    for key, raw in form.multi_items():
        m = _TERM_FIELD_RE.match(key)
        if m is None:
            continue
        idx = int(m.group(1))
        field = m.group(2)
        bucket = by_index.setdefault(
            idx,
            {"sign": "+", "coefficient_percent": "", "source_category_ids": []},
        )
        if field == "source_category_ids":
            bucket["source_category_ids"].append(raw)
        else:
            bucket[field] = raw
    out: list[dict[str, Any]] = []
    for idx in sorted(by_index):
        row = by_index[idx]
        row["source_category_ids"] = tuple(row["source_category_ids"])
        out.append(row)
    return out


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
        categories=categories_repo.list_all(conn, user_id),
        accounts=accounts_repo.list_all(conn, user_id),
        source_categories=_formula_source_candidates(conn, user_id),
        amount_source="fixed",
        terms=[dict(_EMPTY_TERM_INPUT)],
        errors={},
    )


def _validate_cadence(value: str) -> Cadence | None:
    try:
        return Cadence(value)
    except ValueError:
        return None


def _resolve_dest_account(  # noqa: PLR0911 — flat validation surface mirroring transactions router
    conn: sqlite3.Connection,
    user_id: int,
    *,
    dest_account_id_raw: str,
    category: Any,
    source_account: Any,
) -> tuple[int | None, dict[str, str]]:
    """Validate the destination account input (mirrors transactions router).

    Transits (``direction=transit``) require a destination with matching
    currency; non-transit categories ignore any posted value.
    """
    if not dest_account_id_raw:
        if category is not None and category.direction == Direction.TRANSIT:
            return None, {"dest_account_id": "transit requires destination account"}
        return None, {}
    if category is None or category.direction != Direction.TRANSIT:
        return None, {}
    parsed = _parse_int(dest_account_id_raw)
    if parsed is None:
        return None, {"dest_account_id": "invalid destination"}
    dest = accounts_repo.find_by_id(conn, user_id, parsed)
    if dest is None:
        return None, {"dest_account_id": "unknown destination"}
    if source_account is not None and dest.currency != source_account.currency:
        return None, {"dest_account_id": "cross-currency transit not supported"}
    if source_account is not None and dest.id == source_account.id:
        return None, {"dest_account_id": "destination must differ from source"}
    return parsed, {}


def _resolve_amount_inputs(  # noqa: PLR0911 — branchy validation surface
    conn: sqlite3.Connection,
    user_id: int,
    *,
    amount_source: str,
    default_amount: str,
    term_inputs: list[dict[str, Any]],
    account_currency: str | None,
    exclude_rule_id: int | None,
    today: date,
) -> tuple[int | None, AmountFormula | None, dict[str, str]]:
    """Validate fixed-vs-formula branch; return (default_amount_minor, formula, errors)."""
    errors: dict[str, str] = {}
    if amount_source == "formula":
        if account_currency is None:
            errors["amount_source"] = "unknown account currency"
            return None, None, errors
        try:
            terms = [
                formula_svc.build_term(
                    sign=t.get("sign", "+"),
                    coefficient_percent=t.get("coefficient_percent", ""),
                    source_category_ids=[int(v) for v in t.get("source_category_ids", ())],
                )
                for t in term_inputs
            ]
            formula = formula_svc.build_formula(terms)
        except formula_svc.FormulaError as exc:
            errors["formula"] = str(exc)
            return None, None, errors
        try:
            formula_svc.validate_formula_sources(
                conn, user_id, formula, exclude_rule_id=exclude_rule_id
            )
        except formula_svc.FormulaError as exc:
            errors["formula"] = str(exc)
            return None, None, errors
        snapshot = formula_svc.compute_formula_amount(
            conn,
            user_id,
            formula,
            today.year,
            today.month,
            exclude_rule_id=exclude_rule_id,
        )
        return snapshot, formula, errors
    # fixed branch
    if account_currency is None:
        errors["default_amount"] = "unknown account currency"
        return None, None, errors
    try:
        dec = Decimal(default_amount)
    except InvalidOperation:
        errors["default_amount"] = "invalid amount"
        return None, None, errors
    if dec <= 0:
        errors["default_amount"] = "must be positive"
        return None, None, errors
    return to_minor_units(dec, account_currency), None, errors


def _render_form_errors(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    *,
    rule: Any,
    action: str,
    errors: Mapping[str, str],
    amount_source: str,
    terms: list[dict[str, Any]],
) -> Response:
    return render(
        request,
        "partials/recurring/_form.html",
        rule=rule,
        action=action,
        categories=categories_repo.list_all(conn, user_id),
        accounts=accounts_repo.list_all(conn, user_id),
        source_categories=_formula_source_candidates(conn, user_id),
        amount_source=amount_source,
        terms=terms,
        errors=errors,
        status_code=422,
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
    term_inputs = _parse_terms_from_form(form)

    errors: dict[str, str] = {}
    c = _validate_cadence(cadence)
    if c is None:
        errors["cadence"] = "invalid cadence"
    start = _parse_date(start_date)
    if start is None:
        errors["start_date"] = "invalid date"
    end: date | None = None
    if end_date_raw:
        end = _parse_date(end_date_raw)
        if end is None:
            errors["end_date"] = "invalid date"
        elif start is not None and end < start:
            errors["end_date"] = "must be on or after start"
    try:
        category_id = int(category_id_raw)
        account_id = int(account_id_raw)
    except ValueError:
        errors["account_id"] = "invalid account/category"
        return _render_form_errors(
            request,
            conn,
            user_id,
            rule=None,
            action="/recurring",
            errors=errors,
            amount_source=amount_source,
            terms=term_inputs or [dict(_EMPTY_TERM_INPUT)],
        )
    acc = accounts_repo.find_by_id(conn, user_id, account_id)
    cat = categories_repo.find_by_id(conn, user_id, category_id)
    if acc is None:
        errors["account_id"] = "unknown account"
    if cat is None:
        errors["category_id"] = "unknown category"
    dest_id, dest_errors = _resolve_dest_account(
        conn,
        user_id,
        dest_account_id_raw=dest_account_id_raw,
        category=cat,
        source_account=acc,
    )
    errors.update(dest_errors)
    minor, formula, amount_errors = _resolve_amount_inputs(
        conn,
        user_id,
        amount_source=amount_source,
        default_amount=default_amount,
        term_inputs=term_inputs,
        account_currency=acc.currency if acc else None,
        exclude_rule_id=None,
        today=dt.date.today(),  # noqa: DTZ011 — date-only anchor
    )
    errors.update(amount_errors)
    if errors:
        return _render_form_errors(
            request,
            conn,
            user_id,
            rule=None,
            action="/recurring",
            errors=errors,
            amount_source=amount_source,
            terms=term_inputs or [dict(_EMPTY_TERM_INPUT)],
        )
    assert c is not None and start is not None and minor is not None
    today = dt.date.today()  # noqa: DTZ011
    # ADR-0063: a stop date already in the past means the schedule is dead
    # on arrival — insert as inactive so it never shows up in Upcoming
    # or Forecast between create and the first promotion attempt.
    initial_active = not (end is not None and end < today)
    rule = recurring_repo.create_rule(
        conn,
        user_id,
        NewRecurringRule(
            cadence=c,
            start_date=start,
            end_date=end,
            category_id=category_id,
            account_id=account_id,
            dest_account_id=dest_id,
            default_amount=minor,
            default_description=default_description,
            day_of_month=_parse_int(day_of_month),
            amount_formula=formula,
            active=initial_active,
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
    trigger(html, "forecast-stale", "ledger-stale")
    return html


def _formula_prefill(rule: Any) -> tuple[str, list[dict[str, Any]]]:
    """Return (amount_source, term_input_rows) from a persisted rule.

    Fixed-amount rules get a seed empty term so the formula branch can
    receive input immediately on toggle. Formula rules return each term in
    persisted order as a dict shape matching :func:`_parse_terms_from_form`.
    """
    if rule is None or rule.amount_formula is None:
        return "fixed", [dict(_EMPTY_TERM_INPUT)]
    rows: list[dict[str, Any]] = []
    for term in rule.amount_formula.terms:
        pct = (Decimal(term.coefficient_bps) / Decimal(100)).normalize()
        pct_str = format(pct, "f")
        rows.append(
            {
                "sign": term.sign,
                "coefficient_percent": pct_str,
                "source_category_ids": tuple(term.source_category_ids),
            }
        )
    return "formula", rows


# ---------------------------------------------------------------------------
# T-R45 — Batch promote-due (ADR-0056 §6, ADR-0038). Registered BEFORE
# `/{rule_id}` for the same reason as formula/preview.
# ---------------------------------------------------------------------------
def _hx_trigger_payload(payload: dict[str, Any]) -> str:
    """JSON-serialise an HX-Trigger payload mapping event names → data."""
    import json  # noqa: PLC0415

    return json.dumps(payload)


@router.post("/batch/promote-due", response_class=HTMLResponse)
def recurring_batch_promote_due(
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    """Promote every active rule with ``next_due <= today`` in one transaction.

    Returns a 204 with an HX-Trigger carrying the toast + the lists of
    created transaction ids + advanced rule ids so the frontend can wire
    the Undo button to :func:`recurring_batch_undo`.
    """
    today = dt.date.today()  # noqa: DTZ011
    try:
        result = recurring_svc.batch_promote_due(conn, user_id, today)
    except (
        recurring_svc.CannotPromoteSkippedError,
        recurring_svc.InactiveRecurringError,
        UnsupportedDirectionError,
        ValidationError,
    ) as exc:
        return Response(status_code=422, content=str(exc))
    resp = Response(status_code=204)
    resp.headers["HX-Trigger"] = _hx_trigger_payload(
        {
            "toast": {
                "variant": "success",
                "message": (
                    f"Promoted {len(result.promoted_txn_ids)} recurring row(s)"
                    f" (skipped {len(result.skipped_rule_ids)})"
                ),
                "undo_url": "/recurring/batch/undo",
                "undo_payload": {
                    "promoted_txn_ids": list(result.promoted_txn_ids),
                    "advanced_rule_ids": list(result.advanced_rule_ids),
                },
            },
            "ledger-stale": True,
            "forecast-stale": True,
            "budget-stale": True,
            "today-stale": True,
        }
    )
    return resp


@router.post("/batch/undo", response_class=HTMLResponse)
async def recurring_batch_undo(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    """Reverse a prior batch recurring promote.

    Expects form fields ``promoted_txn_ids`` (CSV of ints) and
    ``advanced_rule_ids`` (CSV of ints). Soft-deletes the promoted txns
    + reverts each rule's ``next_due`` from its most recent
    audit_log entry.
    """
    from budget_planner.repositories import (  # noqa: PLC0415
        recurring as recurring_repo_mod,
        transactions as transactions_repo,
    )
    from budget_planner.repositories._shared import transaction as db_transaction  # noqa: PLC0415

    form = await request.form()
    try:
        txn_ids = [int(v) for v in str(form.get("promoted_txn_ids", "")).split(",") if v]
        rule_ids = [int(v) for v in str(form.get("advanced_rule_ids", "")).split(",") if v]
    except ValueError:
        return Response(status_code=422, content="invalid id list")

    with db_transaction(conn):
        for txn_id in txn_ids:
            transactions_repo.soft_delete(conn, user_id, txn_id)
        for rule_id in rule_ids:
            # Replay audit: the batch wrote a `recurring_rule` update row
            # for each advancement with the prior rule state in ``prev_json``.
            row = conn.execute(
                """
                SELECT prev_json FROM audit_log
                WHERE entity_type = 'recurring_rule' AND entity_id = ?
                ORDER BY id DESC LIMIT 1
                """,
                (rule_id,),
            ).fetchone()
            if row is None or row["prev_json"] is None:
                continue
            import json  # noqa: PLC0415

            prev = json.loads(row["prev_json"])
            prev_next_due_raw = prev.get("next_due")
            prev_last_promoted = prev.get("last_promoted_date")
            if not prev_next_due_raw:
                continue
            prev_next_due = date.fromisoformat(prev_next_due_raw)
            prev_last_promoted_date = (
                date.fromisoformat(prev_last_promoted) if prev_last_promoted else None
            )
            recurring_repo_mod.set_next_due(
                conn,
                user_id,
                rule_id,
                next_due=prev_next_due,
                last_promoted_date=prev_last_promoted_date,
            )
    resp = Response(status_code=204)
    resp.headers["HX-Trigger"] = _hx_trigger_payload(
        {
            "toast": {"variant": "info", "message": "Undone"},
            "ledger-stale": True,
            "forecast-stale": True,
            "budget-stale": True,
            "today-stale": True,
        }
    )
    return resp


# ---------------------------------------------------------------------------
# T-R41 — Formula preview (ADR-0056 §4). Registered BEFORE `/{rule_id}` so
# FastAPI's int-path validator does not swallow the literal `formula` segment.
# ---------------------------------------------------------------------------
@router.post("/formula/preview", response_class=HTMLResponse)
async def formula_preview(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    """Return the live-preview chip or inline error for a draft formula.

    No DB write; shares the save-path primitives via
    ``services.recurring_formula.preview``. Accepts the same
    ``terms[i][field]`` form shape as the create / update routes.
    """
    form = await request.form()
    draft_rule_id_raw = str(form.get("draft_rule_id", ""))
    draft_rule_id: int | None = None
    if draft_rule_id_raw:
        parsed = _parse_int(draft_rule_id_raw)
        if parsed is None:
            return Response(status_code=422, content="invalid draft_rule_id")
        draft_rule_id = parsed
    term_inputs = _parse_terms_from_form(form)
    drafts: list[formula_svc.DraftTerm] = []
    for row in term_inputs:
        try:
            cat_ids = tuple(int(v) for v in row.get("source_category_ids", ()))
        except (TypeError, ValueError):
            return Response(status_code=422, content="invalid source_category_ids")
        drafts.append(
            formula_svc.DraftTerm(
                sign=str(row.get("sign", "+")),
                coefficient_percent=str(row.get("coefficient_percent", "")),
                source_category_ids=cat_ids,
            )
        )
    today = dt.date.today()  # noqa: DTZ011 — date-only anchor
    result = formula_svc.preview(conn, user_id, today, draft_rule_id, drafts)
    status = 200 if isinstance(result, formula_svc.PreviewOk) else 422
    return render(
        request,
        "partials/recurring/_formula_preview.html",
        result=result,
        is_ok=isinstance(result, formula_svc.PreviewOk),
        status_code=status,
    )


@router.get("/{rule_id}/edit", response_class=HTMLResponse)
def edit_form(
    rule_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    rule = recurring_repo.find_rule(conn, user_id, rule_id)
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
            terms=[dict(_EMPTY_TERM_INPUT)],
            errors={"rule": "not found"},
            status_code=404,
        )
    amount_source, terms = _formula_prefill(rule)
    # T-114 / ADR-0030 §4 — slide-over wrapper mirrors /recurring/new.
    return render(
        request,
        "partials/_slideover.html",
        slide_over_title="Edit recurring rule",
        form_include="partials/recurring/_form.html",
        rule=rule,
        action=f"/recurring/{rule_id}",
        categories=categories_repo.list_all(conn, user_id),
        accounts=accounts_repo.list_all(conn, user_id),
        source_categories=_formula_source_candidates(conn, user_id),
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
    rule = recurring_repo.find_rule(conn, user_id, rule_id)
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
    term_inputs = _parse_terms_from_form(form)
    try:
        category_id = int(category_id_raw)
        account_id = int(account_id_raw)
    except ValueError:
        return Response(status_code=422, content="invalid account/category")
    acc = accounts_repo.find_by_id(conn, user_id, account_id)
    cat = categories_repo.find_by_id(conn, user_id, category_id)
    c = _validate_cadence(cadence)
    start = _parse_date(start_date)
    end: date | None = None
    errors: dict[str, str] = {}
    if c is None:
        errors["cadence"] = "invalid"
    if start is None:
        errors["start_date"] = "invalid date"
    if end_date_raw:
        end = _parse_date(end_date_raw)
        if end is None:
            errors["end_date"] = "invalid date"
        elif start is not None and end < start:
            errors["end_date"] = "must be on or after start"
    if acc is None:
        errors["account_id"] = "unknown account"
    if cat is None:
        errors["category_id"] = "unknown category"
    dest_id, dest_errors = _resolve_dest_account(
        conn,
        user_id,
        dest_account_id_raw=dest_account_id_raw,
        category=cat,
        source_account=acc,
    )
    errors.update(dest_errors)
    minor, formula, amount_errors = _resolve_amount_inputs(
        conn,
        user_id,
        amount_source=amount_source,
        default_amount=default_amount,
        term_inputs=term_inputs,
        account_currency=acc.currency if acc else None,
        exclude_rule_id=rule_id,
        today=dt.date.today(),  # noqa: DTZ011
    )
    errors.update(amount_errors)
    if errors:
        return _render_form_errors(
            request,
            conn,
            user_id,
            rule=rule,
            action=f"/recurring/{rule_id}",
            errors=errors,
            amount_source=amount_source,
            terms=term_inputs or [dict(_EMPTY_TERM_INPUT)],
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
    recurring_repo.update_rule(
        conn,
        user_id,
        rule_id,
        PatchRecurringRule(**patch_kwargs),
    )
    updated = recurring_repo.find_rule(conn, user_id, rule_id)
    assert updated is not None and acc is not None
    cat = categories_repo.find_by_id(conn, user_id, updated.category_id)
    html = render(
        request,
        "partials/recurring/_row.html",
        rule=updated,
        overrides=recurring_repo.list_overrides(conn, user_id, rule_id),
        account=acc,
        category=cat,
        effective_amount_minor=minor,
    )
    trigger(html, "forecast-stale", "ledger-stale")
    return html


def _effective_amount_for_render(
    conn: sqlite3.Connection,
    user_id: int,
    rule: Any,
) -> int:
    """Return the amount to render in the Ledger row for a rule (formula-aware)."""
    return formula_svc.resolve_rule_amount(conn, user_id, rule, rule.next_due)


@router.post("/{rule_id}/deactivate")
def deactivate_rule(
    rule_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    rule = recurring_repo.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    recurring_repo.deactivate_rule(conn, user_id, rule_id)
    # Empty body + ledger-stale trigger removes the row from the Ledger
    # Recurring tab (hx-swap="outerHTML") and re-fetches the table so
    # inactive rules disappear from view. Mirrors transactions/delete.
    resp = Response(content="", media_type="text/html")
    trigger(resp, "ledger-stale", "forecast-stale")
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
    rule = recurring_repo.find_rule(conn, user_id, rule_id)
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
    account = accounts_repo.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    default_amount_str = f"{Decimal(rule.default_amount) / Decimal(100):.2f}" if account else ""
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
def add_override(  # noqa: PLR0917, PLR0911
    rule_id: int,
    request: Request,
    year: int = Form(...),
    month: int = Form(...),
    amount: str = Form(...),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    rule = recurring_repo.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    if not (1900 <= year <= 9999 and 1 <= month <= 12):  # noqa: PLR2004
        return Response(status_code=422, content="invalid year or month")
    occ = recurring_svc.occurrence_in_month(rule, year, month)
    if occ is None:
        return Response(
            status_code=422,
            content=f"rule has no occurrence in {year:04d}-{month:02d}",
        )
    acc = accounts_repo.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    if acc is None:
        return Response(status_code=422, content="rule has no live account")
    try:
        dec = Decimal(amount.replace(",", "."))
    except InvalidOperation:
        return Response(status_code=422, content="invalid amount")
    if dec <= 0:
        return Response(status_code=422, content="amount must be positive")
    amount_minor = to_minor_units(dec, acc.currency)
    recurring_repo.upsert_override(
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
    overrides = recurring_repo.list_overrides(conn, user_id, rule_id)
    acc = accounts_repo.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    cat = categories_repo.find_by_id(conn, user_id, rule.category_id, include_deleted=True)
    html = render(
        request,
        "partials/recurring/_row.html",
        rule=rule,
        overrides=overrides,
        account=acc,
        category=cat,
        effective_amount_minor=_effective_amount_for_render(conn, user_id, rule),
    )
    trigger(html, "forecast-stale", "ledger-stale")
    return html


@router.post("/{rule_id}/overrides/{occurrence_date}/delete")
def delete_override(
    rule_id: int,
    occurrence_date: str,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    rule = recurring_repo.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    occ = _parse_date(occurrence_date)
    if occ is None:
        return Response(status_code=422, content="invalid date")
    recurring_repo.delete_override(conn, user_id, rule_id, occ)
    overrides = recurring_repo.list_overrides(conn, user_id, rule_id)
    acc = accounts_repo.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    cat = categories_repo.find_by_id(conn, user_id, rule.category_id, include_deleted=True)
    html = render(
        request,
        "partials/recurring/_row.html",
        rule=rule,
        effective_amount_minor=_effective_amount_for_render(conn, user_id, rule),
        overrides=overrides,
        account=acc,
        category=cat,
    )
    trigger(html, "forecast-stale", "ledger-stale")
    return html


# ---------------------------------------------------------------------------
# T-118 — Promote / Skip-next (ADR-0038)
# ---------------------------------------------------------------------------
def _override_on_next_due(
    conn: sqlite3.Connection,
    user_id: int,
    rule_id: int,
    next_due: date,
) -> RecurringOverride | None:
    """Return the override whose canonical ``occurrence_date == next_due``."""
    for override in recurring_repo.list_overrides(conn, user_id, rule_id):
        if override.occurrence_date == next_due:
            return override
    return None


def _render_promote_modal(
    request: Request,
    conn: sqlite3.Connection,
    user_id: int,
    rule_id: int,
    *,
    errors: dict[str, str] | None = None,
    status_code: int = 200,
) -> Response:
    rule = recurring_repo.find_rule(conn, user_id, rule_id)
    if rule is None:
        return render(
            request,
            "partials/recurring/_promote_modal.html",
            rule=None,
            account=None,
            override=None,
            prefill_date=None,
            prefill_amount_minor=None,
            prefill_description="",
            errors={"rule": "not found"},
            status_code=404,
        )
    override = _override_on_next_due(conn, user_id, rule_id, rule.next_due)
    account = accounts_repo.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
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
        "partials/recurring/_promote_modal.html",
        rule=rule,
        account=account,
        override=override,
        prefill_date=prefill_date,
        prefill_amount_minor=prefill_amount,
        prefill_description=prefill_description,
        errors=errors or {},
        status_code=status_code,
    )


@router.get("/{rule_id}/promote", response_class=HTMLResponse)
def promote_form(
    rule_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    return _render_promote_modal(request, conn, user_id, rule_id)


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
    rule = recurring_repo.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    account = accounts_repo.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    occurrence = _parse_date(date) or rule.next_due
    override = _override_on_next_due(conn, user_id, rule_id, occurrence)
    prefill_amount = formula_svc.resolve_rule_amount(conn, user_id, rule, occurrence)
    prefill_description = rule.default_description
    if override is not None:
        if override.amount_override is not None:
            prefill_amount = override.amount_override
        if override.description_override is not None:
            prefill_description = override.description_override
    categories_by_id = {c.id: c for c in categories_repo.list_all(conn, user_id)}
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
def promote_submit(  # noqa: PLR0912, PLR0917
    rule_id: int,
    request: Request,
    operation_date: str = Form(""),
    amount: str = Form(""),
    description: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    rule = recurring_repo.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    account = accounts_repo.find_by_id(conn, user_id, rule.account_id, include_deleted=True)
    errors: dict[str, str] = {}

    op_date: date | None = None
    if operation_date:
        op_date = _parse_date(operation_date)
        if op_date is None:
            errors["operation_date"] = "invalid date"

    amount_minor: int | None = None
    if amount:
        if account is None:
            errors["amount"] = "unknown account currency"
        else:
            try:
                dec = Decimal(amount)
            except (InvalidOperation, TypeError):
                errors["amount"] = "amount must be a decimal number"
            else:
                if dec <= 0:
                    errors["amount"] = "amount must be positive"
                else:
                    amount_minor = to_minor_units(dec, account.currency)

    if errors:
        return _render_promote_modal(
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
        return _render_promote_modal(
            request,
            conn,
            user_id,
            rule_id,
            errors={"promotion": str(exc)},
            status_code=422,
        )

    updated = recurring_repo.find_rule(conn, user_id, rule_id, include_deleted=True)
    assert updated is not None
    acc = accounts_repo.find_by_id(conn, user_id, updated.account_id, include_deleted=True)
    cat = categories_repo.find_by_id(conn, user_id, updated.category_id, include_deleted=True)
    html = render(
        request,
        "partials/recurring/_row.html",
        rule=updated,
        overrides=recurring_repo.list_overrides(conn, user_id, rule_id),
        account=acc,
        category=cat,
        effective_amount_minor=_effective_amount_for_render(conn, user_id, updated),
    )
    trigger(html, "ledger-stale", "forecast-stale", "budget-stale")
    return html


@router.post("/{rule_id}/skip-next")
def skip_next(
    rule_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    rule = recurring_repo.find_rule(conn, user_id, rule_id)
    if rule is None:
        return Response(status_code=404, content="not found")
    try:
        recurring_svc.skip_and_advance(conn, user_id, rule_id)
    except recurring_svc.InactiveRecurringError:
        return Response(status_code=422, content="rule is inactive")
    updated = recurring_repo.find_rule(conn, user_id, rule_id, include_deleted=True)
    assert updated is not None
    acc = accounts_repo.find_by_id(conn, user_id, updated.account_id, include_deleted=True)
    cat = categories_repo.find_by_id(conn, user_id, updated.category_id, include_deleted=True)
    html = render(
        request,
        "partials/recurring/_row.html",
        rule=updated,
        overrides=recurring_repo.list_overrides(conn, user_id, rule_id),
        account=acc,
        category=cat,
        effective_amount_minor=_effective_amount_for_render(conn, user_id, updated),
    )
    trigger(html, "ledger-stale", "forecast-stale", "budget-stale")
    return html
