"""Admin-only user roster at ``/settings/users`` (T-D17, T-UR14; ADR-0061, ADR-0073, ADR-0152).

Thin layer over :mod:`budget_planner.services.users`. ``AdminRequiredMiddleware``
already answers 404 to non-admins. The :func:`~budget_planner.web.auth_deps.current_admin`
dependency repeats that check in case the router is ever mounted without it.
Renderers live in :mod:`budget_planner.web.users_admin` (T-Q267).

HTMX contract (``fragments/dialogs/*``, ``fragments/rows/user-row``):

- Edit, reset password and delete open dialogs in ``#modal-root`` (``GET .../edit``,
  ``.../reset-password``, ``.../delete``); delete shows the blocked variant when a service
  guard (own account, last admin) would refuse.
- Edit swaps the saved row and flashes success; delete removes the row and flashes.
- Add (``GET .../new``, then ``POST``; a 422 re-opens the add dialog with the field errors) and
  reset answer with the one-time password dialog and the refreshed table out of band. The
  response is ``no-store``.
- 422 (invalid / duplicate email, or an edit that changes the email) re-renders the dialog
  with the field summary. 409 (last admin, self-demotion, self-removal) is a flash with
  ``HX-Reswap: none`` and closes the dialog.

Non-HTMX fallbacks: create / reset re-render the full page with the password inline (no
redirect, so the password is not lost); edit / delete redirect 303 back to the list.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from http import HTTPStatus

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, Response

from budget_planner.domain.ports import PasswordHasher, TokenSource
from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.services import invites as invites_service, users as users_service
from budget_planner.services.users import UserConflict, UserInputError, UserNotFound
from budget_planner.web.auth_deps import current_admin
from budget_planner.web.deps import (
    get_db,
    get_password_hasher,
    get_request_ctx,
    get_token_source,
    reauth_now,
    require_recent_auth,
)
from budget_planner.web.dialogs import dialog_response, invalid_dialog_response, saved_response
from budget_planner.web.field_labels import field_summary
from budget_planner.web.invites_admin import (
    CREATE_DIALOG,
    REVOKE_DIALOG,
    create_context,
    invite_not_found,
    link_response,
)
from budget_planner.web.middleware.auth import CurrentUser
from budget_planner.web.rendering import is_hx_request, render, render_context
from budget_planner.web.users_admin import (
    ADD_DIALOG,
    DELETE_DIALOG,
    EDIT_DIALOG,
    LIST_PATH,
    LIST_TEMPLATE,
    RESET_DIALOG,
    ROW_TEMPLATE,
    add_context,
    checkbox,
    conflict,
    conflict_message,
    dialog_view,
    not_found,
    page_context,
    password_toast,
    render_toast,
    row_context,
    see_other,
    user_dialog,
)

router = APIRouter(prefix=LIST_PATH, tags=["settings-users"])


@router.get("", response_class=HTMLResponse)
def list_users(
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
) -> HTMLResponse:
    """Roster page: every live user; other users' rows carry the edit / reset / delete menu."""
    return render_context(request, LIST_TEMPLATE, page_context(request, conn, admin))


@router.post("", response_class=HTMLResponse, dependencies=[Depends(require_recent_auth)])
def create_user(
    request: Request,
    *,
    email: str = Form(default=""),
    name: str = Form(default=""),
    is_admin: str | None = Form(default=None),
    role: str = Form(default="member"),
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
    request_ctx: RequestCtx = Depends(get_request_ctx),
    tokens: TokenSource = Depends(get_token_source),
    hasher: PasswordHasher = Depends(get_password_hasher),
) -> HTMLResponse:
    """Create a user; the add dialog answers with the one-time password dialog (shown once)."""
    admin_flag = checkbox(is_admin) or role == "admin"
    try:
        draft = users_service.build_draft(email=email, name=name, is_admin=admin_flag)
        user, password = users_service.create_user(
            conn, admin.id, draft, tokens=tokens, hasher=hasher, request_ctx=request_ctx
        )
    except UserInputError as exc:
        if is_hx_request(request):
            return invalid_dialog_response(
                request,
                ADD_DIALOG,
                add_context(email=email, name=name, is_admin=admin_flag),
                exc.fields,
            )
        rows = field_summary(exc.fields)
        context = {**page_context(request, conn, admin), "form_summary": rows}
        return render(request, LIST_TEMPLATE, HTTPStatus.UNPROCESSABLE_ENTITY, **context)
    return render_toast(request, conn, admin, password_toast(user, password, kind="created"))


@router.get("/new", response_class=HTMLResponse, dependencies=[Depends(current_admin)])
def add_form(request: Request) -> HTMLResponse:
    """Add user dialog (email, name, role)."""
    return dialog_response(request, ADD_DIALOG, add_context())


# --- invites (T-UR20a): before the ``/{user_id}`` routes so ``invites`` is not read as an id ---


@router.get("/invites/new", response_class=HTMLResponse, dependencies=[Depends(current_admin)])
def invite_new(request: Request) -> HTMLResponse:
    """Create invite dialog (email and role)."""
    return dialog_response(request, CREATE_DIALOG, create_context())


@router.post("/invites", response_model=None, dependencies=[Depends(require_recent_auth)])
def invite_create(
    request: Request,
    *,
    email: str = Form(default=""),
    role: str = Form(default="member"),
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
    request_ctx: RequestCtx = Depends(get_request_ctx),
    tokens: TokenSource = Depends(get_token_source),
    now: datetime = Depends(reauth_now),
) -> Response:
    """Create an invite and show its link once."""
    is_admin = role == "admin"
    try:
        issued = invites_service.create_invite(
            conn,
            admin.id,
            email=email,
            is_admin=is_admin,
            tokens=tokens,
            now=now,
            request_ctx=request_ctx,
        )
    except UserInputError as exc:
        return invalid_dialog_response(
            request, CREATE_DIALOG, create_context(email=email, is_admin=is_admin), exc.fields
        )
    return link_response(request, conn, admin, issued, now=now, resent=False)


@router.get(
    "/invites/{invite_id}/revoke",
    response_class=HTMLResponse,
    dependencies=[Depends(current_admin)],
)
def invite_revoke_form(
    request: Request,
    invite_id: int,
    conn: sqlite3.Connection = Depends(get_db),
) -> HTMLResponse:
    """Revoke confirm dialog."""
    invite = next((i for i in invites_service.list_invites(conn) if i.id == invite_id), None)
    if invite is None:
        return invite_not_found(request)
    return dialog_response(request, REVOKE_DIALOG, {"invite": invite})


@router.post(
    "/invites/{invite_id}/resend", response_model=None, dependencies=[Depends(require_recent_auth)]
)
def invite_resend(
    request: Request,
    invite_id: int,
    *,
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
    request_ctx: RequestCtx = Depends(get_request_ctx),
    tokens: TokenSource = Depends(get_token_source),
    now: datetime = Depends(reauth_now),
) -> Response:
    """New link and a fresh 7 days; the old link stops working."""
    try:
        issued = invites_service.resend_invite(
            conn, admin.id, invite_id, tokens=tokens, now=now, request_ctx=request_ctx
        )
    except invites_service.InviteNotFoundError:
        return invite_not_found(request)
    except invites_service.InviteConflictError as exc:
        return conflict_message(request, exc.message)
    return link_response(request, conn, admin, issued, now=now, resent=True)


@router.post(
    "/invites/{invite_id}/revoke", response_model=None, dependencies=[Depends(require_recent_auth)]
)
def invite_revoke(
    request: Request,
    invite_id: int,
    *,
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
    request_ctx: RequestCtx = Depends(get_request_ctx),
    now: datetime = Depends(reauth_now),
) -> Response:
    """Revoke (final): the link reads ``invalid`` from now on."""
    try:
        invite = invites_service.revoke_invite(
            conn, admin.id, invite_id, now=now, request_ctx=request_ctx
        )
    except invites_service.InviteNotFoundError:
        return invite_not_found(request)
    except invites_service.InviteConflictError as exc:
        return conflict_message(request, exc.message)
    if not is_hx_request(request):
        return see_other()
    return saved_response(request, None, {}, message=f"Revoked the invite for {invite.email}.")


@router.get("/{user_id}/edit", response_class=HTMLResponse)
def edit_form(
    request: Request,
    user_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
) -> HTMLResponse:
    """Edit dialog (name and role; the email is read-only)."""
    try:
        user = users_service.get_live_user(conn, user_id)
    except UserNotFound:
        return not_found(request)
    return user_dialog(request, conn, admin, EDIT_DIALOG, user)


@router.get("/{user_id}/reset-password", response_class=HTMLResponse)
def reset_form(
    request: Request,
    user_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
) -> HTMLResponse:
    """Reset-password confirm dialog."""
    try:
        user = users_service.get_live_user(conn, user_id)
    except UserNotFound:
        return not_found(request)
    return user_dialog(request, conn, admin, RESET_DIALOG, user)


@router.get("/{user_id}/delete", response_class=HTMLResponse)
def delete_form(
    request: Request,
    user_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
) -> HTMLResponse:
    """Delete confirm dialog; the blocked variant when a service guard would refuse."""
    try:
        user = users_service.get_live_user(conn, user_id)
    except UserNotFound:
        return not_found(request)
    return user_dialog(request, conn, admin, DELETE_DIALOG, user)


@router.post("/{user_id}", response_model=None, dependencies=[Depends(require_recent_auth)])
def save_user(
    request: Request,
    user_id: int,
    *,
    email: str = Form(default=""),
    name: str = Form(default=""),
    is_admin: str | None = Form(default=None),
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
    request_ctx: RequestCtx = Depends(get_request_ctx),
) -> Response:
    """Save edits; the email is read-only (422), no self- or last-admin demotion (409)."""
    try:
        target = users_service.get_live_user(conn, user_id)
    except UserNotFound:
        return not_found(request)
    # A missing field means "unchanged" (Q-063); the edit form always sends it.
    admin_flag = None if is_admin is None else checkbox(is_admin)
    try:
        draft = users_service.build_draft(email=email, name=name, is_admin=admin_flag)
        updated = users_service.edit_user(conn, admin.id, user_id, draft, request_ctx=request_ctx)
    except UserInputError as exc:
        view = dialog_view(conn, admin, target, name=name, is_admin=admin_flag)
        return invalid_dialog_response(request, EDIT_DIALOG, {"view": view}, exc.fields)
    except UserConflict as exc:
        return conflict(request, exc)
    except UserNotFound:
        return not_found(request)
    if not is_hx_request(request):
        return see_other()
    return saved_response(
        request,
        ROW_TEMPLATE,
        row_context(request, conn, admin, user_id),
        message=f"Saved {updated.email or updated.name}.",
    )


@router.post(
    "/{user_id}/reset-password",
    response_class=HTMLResponse,
    dependencies=[Depends(require_recent_auth)],
)
def reset_password(
    request: Request,
    user_id: int,
    *,
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
    request_ctx: RequestCtx = Depends(get_request_ctx),
    tokens: TokenSource = Depends(get_token_source),
    hasher: PasswordHasher = Depends(get_password_hasher),
) -> HTMLResponse:
    """Generate a new one-shot password and revoke the target's sessions."""
    try:
        user, password = users_service.reset_password(
            conn, admin.id, user_id, tokens=tokens, hasher=hasher, request_ctx=request_ctx
        )
    except UserNotFound:
        return not_found(request)
    return render_toast(request, conn, admin, password_toast(user, password, kind="reset"))


@router.post("/{user_id}/delete", response_model=None, dependencies=[Depends(require_recent_auth)])
def delete_user(
    request: Request,
    user_id: int,
    conn: sqlite3.Connection = Depends(get_db),
    admin: CurrentUser = Depends(current_admin),
    request_ctx: RequestCtx = Depends(get_request_ctx),
) -> Response:
    """Soft-delete a user and revoke all their sessions (one transaction)."""
    try:
        removed = users_service.soft_delete_user(conn, admin.id, user_id, request_ctx=request_ctx)
    except UserConflict as exc:
        return conflict(request, exc)
    except UserNotFound:
        return not_found(request)
    if not is_hx_request(request):
        return see_other()
    return saved_response(request, None, {}, message=f"Removed {removed.email or removed.name}.")
