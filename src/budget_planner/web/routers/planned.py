"""Planned transactions router (T-034)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from budget_planner.domain.money import to_minor_units
from budget_planner.domain.planned import (
    NewPlannedTransaction,
    PatchPlannedTransaction,
    PlannedFilter,
)
from budget_planner.repositories import (
    accounts as accounts_repo,
    categories as categories_repo,
    planned as planned_repo,
)
from budget_planner.services import export as export_service, planned as planned_service
from budget_planner.web.deps import current_user_id, get_db
from budget_planner.web.htmx import trigger
from budget_planner.web.rendering import render

router = APIRouter(prefix="/planned", tags=["planned"])


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def parse_filter(request: Request) -> PlannedFilter:
    q = request.query_params
    scope = q.get("scope", "all")
    promoted: bool | None = None
    if scope == "unpromoted":
        promoted = False
    return PlannedFilter(
        date_from=_parse_date(q.get("date_from")),
        date_to=_parse_date(q.get("date_to")),
        promoted=promoted,
    )


@router.get("")
def index() -> RedirectResponse:
    """Legacy page URL (T-070).

    Redirects to the unified ledger with the ``planned`` view selected. The
    HTMX fragment alias ``/planned/table`` and the CRUD sub-routes stay live.
    """
    return RedirectResponse(url="/ledger?view=planned", status_code=302)


# ---------------------------------------------------------------------------
# T-R45 — Batch promote-due (ADR-0056 §6, ADR-0012). Registered BEFORE
# the dynamic `/{planned_id}` paths.
# ---------------------------------------------------------------------------
def _hx_trigger_payload(payload: dict[str, object]) -> str:
    import json  # noqa: PLC0415

    return json.dumps(payload)


@router.post("/batch/promote-due", response_class=HTMLResponse)
def planned_batch_promote_due(
    conn: sqlite3.Connection = Depends(get_db), user_id: int = Depends(current_user_id)
) -> Response:
    """Promote every unpromoted planned row with ``operation_date <= today``."""
    today = date.today()  # noqa: DTZ011
    try:
        result = planned_service.batch_promote_due(conn, user_id, today)
    except (
        planned_service.AlreadyPromotedError,
        planned_service.CannotPromoteDeletedError,
        planned_service.UnsupportedDirectionError,
        planned_service.ValidationError,
    ) as exc:
        return Response(status_code=422, content=str(exc))
    resp = Response(status_code=204)
    resp.headers["HX-Trigger"] = _hx_trigger_payload(
        {
            "toast": {
                "variant": "success",
                "message": f"Promoted {len(result.promoted_txn_ids)} planned row(s)",
                "undo_url": "/planned/batch/undo",
                "undo_payload": {
                    "promoted_txn_ids": list(result.promoted_txn_ids),
                    "promoted_planned_ids": list(result.promoted_planned_ids),
                },
            },
            "ledger-stale": True,
            "forecast-stale": True,
            "balance-stale": True,
            "today-stale": True,
        }
    )
    return resp


@router.post("/batch/undo", response_class=HTMLResponse)
async def planned_batch_undo(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    """Reverse a prior batch planned promote.

    Soft-deletes each promoted transaction and clears the corresponding
    ``promoted_to_txn_id`` on each planned row (so the row re-appears as
    "unpromoted" in Upcoming).
    """
    from budget_planner.repositories import transactions as transactions_repo  # noqa: PLC0415
    from budget_planner.repositories._shared import transaction as db_transaction  # noqa: PLC0415

    form = await request.form()
    try:
        txn_ids = [int(v) for v in str(form.get("promoted_txn_ids", "")).split(",") if v]
        planned_ids = [int(v) for v in str(form.get("promoted_planned_ids", "")).split(",") if v]
    except ValueError:
        return Response(status_code=422, content="invalid id list")

    with db_transaction(conn):
        for txn_id in txn_ids:
            transactions_repo.soft_delete(conn, user_id, txn_id)
        for pid in planned_ids:
            # Replay audit: find the entry right before the batch stamping
            # (operation="update" with prev_json carrying the pre-batch state)
            # and restore ``promoted_to_txn_id``.
            row = conn.execute(
                """
                SELECT prev_json FROM audit_log
                WHERE entity_type = 'planned_transaction' AND entity_id = ?
                  AND operation = 'update'
                ORDER BY id DESC LIMIT 1
                """,
                (pid,),
            ).fetchone()
            if row is None or row["prev_json"] is None:
                continue
            import json  # noqa: PLC0415

            prev = json.loads(row["prev_json"])
            prev_txn_id = prev.get("promoted_to_txn_id")
            conn.execute(
                "UPDATE planned_transactions SET promoted_to_txn_id = ?, "
                "updated_at = (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')) "
                "WHERE id = ? AND user_id = ?",
                (prev_txn_id, pid, user_id),
            )
    resp = Response(status_code=204)
    resp.headers["HX-Trigger"] = _hx_trigger_payload(
        {
            "toast": {"variant": "info", "message": "Undone"},
            "ledger-stale": True,
            "forecast-stale": True,
            "balance-stale": True,
            "today-stale": True,
        }
    )
    return resp


@router.get("/table", response_class=HTMLResponse)
def table_fragment(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    """Legacy fragment alias (T-064).

    Delegates to the unified ledger fragment with ``view=planned``.
    """
    from budget_planner.web.routers.ledger import render_table_for  # noqa: PLC0415

    return render_table_for(request, conn, user_id, "planned")


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
        slide_over_title="New planned transaction",
        form_include="partials/planned/_form.html",
        planned=None,
        action="/planned",
        categories=categories_repo.list_all(conn, user_id),
        accounts=accounts_repo.list_all(conn, user_id),
        errors={},
    )


def _validate_amount(amount: str, currency: str) -> tuple[int | None, str | None]:
    try:
        dec = Decimal(amount)
    except (InvalidOperation, TypeError):
        return None, "amount must be a decimal number"
    if dec <= 0:
        return None, "amount must be positive"
    return to_minor_units(dec, currency), None


@router.post("")
def create_planned(  # noqa: PLR0917
    request: Request,
    operation_date: str = Form(...),
    category_id: int = Form(...),
    account_id: int = Form(...),
    amount: str = Form(...),
    description: str = Form(""),
    dest_account_id: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    errors: dict[str, str] = {}
    op_date = _parse_date(operation_date)
    if op_date is None:
        errors["operation_date"] = "invalid date"
    acc = accounts_repo.find_by_id(conn, user_id, account_id)
    cat = categories_repo.find_by_id(conn, user_id, category_id)
    if acc is None:
        errors["account_id"] = "unknown account"
    if cat is None:
        errors["category_id"] = "unknown category"
    dest_id: int | None = None
    if dest_account_id.strip():
        try:
            dest_id = int(dest_account_id)
        except ValueError:
            errors["dest_account_id"] = "invalid dest account"
        else:
            if accounts_repo.find_by_id(conn, user_id, dest_id) is None:
                errors["dest_account_id"] = "unknown dest account"
    minor: int | None = None
    if acc is not None:
        minor, err = _validate_amount(amount, acc.currency)
        if err:
            errors["amount"] = err
    if errors:
        return render(
            request,
            "partials/planned/_form.html",
            planned=None,
            action="/planned",
            categories=categories_repo.list_all(conn, user_id),
            accounts=accounts_repo.list_all(conn, user_id),
            errors=errors,
            status_code=422,
        )
    assert op_date is not None and minor is not None
    pl = planned_repo.create(
        conn,
        user_id,
        NewPlannedTransaction(
            operation_date=op_date,
            category_id=category_id,
            account_id=account_id,
            amount=minor,
            description=description,
            dest_account_id=dest_id,
        ),
    )
    html = render(request, "partials/planned/_row.html", view=_from_persisted(pl, acc, cat))
    trigger(html, "forecast-stale", "ledger-stale")
    return html


def _from_persisted(pl: Any, acc: Any, cat: Any) -> dict[str, Any]:
    return {
        "key": f"p-{pl.id}",
        "kind": "persisted",
        "operation_date": pl.operation_date,
        "amount_minor": pl.amount,
        "description": pl.description,
        "is_promoted": pl.promoted_to_txn_id is not None,
        "account": acc,
        "category": cat,
        "persisted_id": pl.id,
        "currency": acc.currency if acc else "",
    }


@router.get("/{planned_id}/edit", response_class=HTMLResponse)
def edit_form(
    planned_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    pl = planned_repo.find_by_id(conn, user_id, planned_id)
    if pl is None:
        return render(
            request,
            "partials/planned/_form.html",
            planned=None,
            action="",
            categories=[],
            accounts=[],
            errors={"planned": "not found"},
            status_code=404,
        )
    # T-114 / ADR-0030 §4 — slide-over wrapper mirrors /planned/new.
    return render(
        request,
        "partials/_slideover.html",
        slide_over_title="Edit planned transaction",
        form_include="partials/planned/_form.html",
        planned=pl,
        action=f"/planned/{planned_id}",
        categories=categories_repo.list_all(conn, user_id),
        accounts=accounts_repo.list_all(conn, user_id),
        errors={},
    )


@router.post("/{planned_id}")
def update_planned(  # noqa: PLR0917
    planned_id: int,
    request: Request,
    operation_date: str = Form(...),
    category_id: int = Form(...),
    account_id: int = Form(...),
    amount: str = Form(...),
    description: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    pl = planned_repo.find_by_id(conn, user_id, planned_id)
    if pl is None:
        return Response(status_code=404, content="not found")
    acc = accounts_repo.find_by_id(conn, user_id, account_id)
    errors: dict[str, str] = {}
    op_date = _parse_date(operation_date)
    if op_date is None:
        errors["operation_date"] = "invalid date"
    if acc is None:
        errors["account_id"] = "unknown account"
    minor: int | None = None
    if acc is not None:
        minor, err = _validate_amount(amount, acc.currency)
        if err:
            errors["amount"] = err
    if errors:
        return render(
            request,
            "partials/planned/_form.html",
            planned=pl,
            action=f"/planned/{planned_id}",
            categories=categories_repo.list_all(conn, user_id),
            accounts=accounts_repo.list_all(conn, user_id),
            errors=errors,
            status_code=422,
        )
    assert op_date is not None and minor is not None
    planned_repo.update(
        conn,
        user_id,
        planned_id,
        PatchPlannedTransaction(
            operation_date=op_date,
            category_id=category_id,
            account_id=account_id,
            amount=minor,
            description=description,
        ),
    )
    updated = planned_repo.find_by_id(conn, user_id, planned_id)
    assert updated is not None and acc is not None
    cat = categories_repo.find_by_id(conn, user_id, updated.category_id)
    html = render(request, "partials/planned/_row.html", view=_from_persisted(updated, acc, cat))
    trigger(html, "forecast-stale", "ledger-stale")
    return html


@router.post("/{planned_id}/delete")
def delete_planned(
    planned_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    pl = planned_repo.find_by_id(conn, user_id, planned_id)
    if pl is None:
        return Response(status_code=404, content="not found")
    planned_repo.soft_delete(conn, user_id, planned_id)
    resp = Response(content="", media_type="text/html")
    trigger(resp, "forecast-stale", "ledger-stale")
    return resp


@router.post("/{planned_id}/restore")
def restore_planned(
    planned_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    """T-R70 — undo a soft-delete (ADR-0019)."""
    try:
        planned_repo.undelete(conn, user_id, planned_id)
    except LookupError:
        return Response(status_code=404, content="not found")
    resp = Response(content="", media_type="text/html")
    trigger(resp, "forecast-stale", "ledger-stale")
    return resp


@router.get("/{planned_id}/promote", response_class=HTMLResponse)
def promote_form(
    planned_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> HTMLResponse:
    pl = planned_repo.find_by_id(conn, user_id, planned_id)
    if pl is None:
        return render(
            request,
            "partials/planned/_promote_modal.html",
            planned=None,
            errors={"planned": "not found"},
            status_code=404,
        )
    acc = accounts_repo.find_by_id(conn, user_id, pl.account_id)
    return render(
        request,
        "partials/planned/_promote_modal.html",
        planned=pl,
        account=acc,
        errors={},
    )


@router.get("/{planned_id}/promote/inline", response_class=HTMLResponse)
def promote_inline(
    planned_id: int,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    """F-02 — Row-expand inline Promote form for Today Upcoming."""
    pl = planned_repo.find_by_id(conn, user_id, planned_id)
    if pl is None:
        return Response(status_code=404, content="not found")
    acc = accounts_repo.find_by_id(conn, user_id, pl.account_id)
    categories_by_id = {c.id: c for c in categories_repo.list_all(conn, user_id)}
    return render(
        request,
        "partials/planned/_promote_inline_row.html",
        planned=pl,
        account=acc,
        categories_by_id=categories_by_id,
    )


@router.post("/{planned_id}/promote")
def promote_submit(  # noqa: PLR0917
    planned_id: int,
    request: Request,
    operation_date: str = Form(...),
    amount: str = Form(...),
    description: str = Form(""),
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    pl = planned_repo.find_by_id(conn, user_id, planned_id)
    if pl is None:
        return Response(status_code=404, content="not found")
    acc = accounts_repo.find_by_id(conn, user_id, pl.account_id)
    op_date = _parse_date(operation_date)
    errors: dict[str, str] = {}
    if op_date is None:
        errors["operation_date"] = "invalid date"
    minor: int | None = None
    if acc is not None:
        minor, err = _validate_amount(amount, acc.currency)
        if err:
            errors["amount"] = err
    if errors:
        return render(
            request,
            "partials/planned/_promote_modal.html",
            planned=pl,
            account=acc,
            errors=errors,
            status_code=422,
        )
    assert op_date is not None and minor is not None
    try:
        planned_service.promote_to_actual(
            conn,
            user_id,
            planned_id,
            planned_service.PromotionEdits(
                operation_date=op_date,
                amount_minor=minor,
                description=description or None,
            ),
        )
    except (
        planned_service.AlreadyPromotedError,
        planned_service.CannotPromoteDeletedError,
        planned_service.UnsupportedDirectionError,
        planned_service.ValidationError,
    ) as exc:
        return render(
            request,
            "partials/planned/_promote_modal.html",
            planned=pl,
            account=acc,
            errors={"promotion": str(exc)},
            status_code=422,
        )
    cat = categories_repo.find_by_id(conn, user_id, pl.category_id)
    pl2 = planned_repo.find_by_id(conn, user_id, planned_id, include_deleted=True)
    assert pl2 is not None
    html = render(request, "partials/planned/_row.html", view=_from_persisted(pl2, acc, cat))
    trigger(html, "balance-stale", "forecast-stale", "ledger-stale")
    return html


@router.get("/export")
def export(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    user_id: int = Depends(current_user_id),
) -> Response:
    fmt = request.query_params.get("format", "csv")
    flt = parse_filter(request)
    views = list(planned_service.list_planned(conn, user_id, flt))
    rows = [
        {
            "key": v.persisted_id if v.persisted_id is not None else -1,
            "operation_date": v.operation_date,
            "amount_minor": v.amount_minor,
            "description": v.description,
            "kind": str(v.kind),
            "is_promoted": v.is_promoted,
        }
        for v in views
    ]
    columns = [
        export_service.ExportColumn(key="key", header="id", kind="int"),
        export_service.ExportColumn(key="operation_date", header="date", kind="date"),
        export_service.ExportColumn(key="amount_minor", header="amount_minor", kind="money_minor"),
        export_service.ExportColumn(key="description", header="description", kind="str"),
        export_service.ExportColumn(key="kind", header="kind", kind="str"),
        export_service.ExportColumn(key="is_promoted", header="promoted", kind="bool"),
    ]
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    if fmt == "parquet":
        return Response(
            content=export_service.export_parquet(rows, columns),
            media_type="application/vnd.apache.parquet",
            headers={"Content-Disposition": f'attachment; filename="planned_{stamp}.parquet"'},
        )
    return Response(
        content=export_service.export_csv(rows, columns),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="planned_{stamp}.csv"'},
    )
