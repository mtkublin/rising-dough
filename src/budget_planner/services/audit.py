"""Canonical audit helper (T-028).

This module formalises the audit-row contract. Repository mutations call
``_shared.write_audit`` indirectly via ``_shared.mutate`` (ADR-0022); any
future caller that needs to emit an audit row MUST go through
``services.audit.write_audit`` so the shape invariants below are enforced
in one place.

Operation shape rules (ADR-0019):

    operation   prev        new
    create      None        required
    update      required    required
    delete      required    None
    undelete    None        required

The caller is responsible for opening (and committing / rolling back) a
transaction around the write.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any, Literal, cast

from budget_planner.domain.request_ctx import RequestCtx
from budget_planner.repositories._shared import write_audit as _write_audit_row

# Module-level singleton for the default empty context — ruff B008 would
# otherwise flag ``RequestCtx.empty()`` inline in parameter defaults.
# ``RequestCtx`` is frozen; sharing one instance across callers is safe.
_EMPTY_REQUEST_CTX: RequestCtx = RequestCtx.empty()

AuditOperation = Literal["create", "update", "delete", "undelete"]


class AuditShapeError(ValueError):
    """Raised when an audit call violates the operation / prev / new contract."""


# ``prev_required`` / ``new_required`` per operation, matching ADR-0019.
_SHAPE_RULES: dict[str, tuple[bool, bool]] = {
    "create": (False, True),
    "update": (True, True),
    "delete": (True, False),
    "undelete": (False, True),
}


def _check_shape(
    operation: AuditOperation,
    prev: Mapping[str, Any] | Any | None,
    new: Mapping[str, Any] | Any | None,
) -> None:
    if operation not in _SHAPE_RULES:
        raise AuditShapeError(f"unknown audit operation: {operation!r}")
    prev_required, new_required = _SHAPE_RULES[operation]
    if prev_required and prev is None:
        raise AuditShapeError(f"operation={operation!r} requires prev is not None")
    if not prev_required and prev is not None:
        raise AuditShapeError(f"operation={operation!r} requires prev is None")
    if new_required and new is None:
        raise AuditShapeError(f"operation={operation!r} requires new is not None")
    if not new_required and new is not None:
        raise AuditShapeError(f"operation={operation!r} requires new is None")


def write_audit(
    conn: sqlite3.Connection,
    *,
    entity_type: str,
    entity_id: int,
    operation: AuditOperation,
    prev: Mapping[str, Any] | Any | None,
    new: Mapping[str, Any] | Any | None,
    request_ctx: RequestCtx = _EMPTY_REQUEST_CTX,
) -> None:
    """Validate shape then insert a single ``audit_log`` row.

    Must be called inside the caller's transaction. Does not commit.

    ``request_ctx`` is forwarded to the row writer; defaults to
    :meth:`RequestCtx.empty` so existing callers that have not been
    plumbed through for T-D14 keep working — the four request-context
    columns land as NULL, matching the pre-migration-0013 shape.
    """
    _check_shape(operation, prev, new)
    _write_audit_row(
        conn,
        entity_type=entity_type,
        entity_id=entity_id,
        operation=cast(str, operation),
        prev=prev,
        new=new,
        request_ctx=request_ctx,
    )


__all__ = ["AuditOperation", "AuditShapeError", "write_audit"]
