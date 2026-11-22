"""Audit entry entity (ADR-0019)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from budget_planner.domain.enums import AuditOperation

if TYPE_CHECKING:
    from _typeshed import DataclassInstance

#: What an audit row may carry as ``prev`` / ``new``: a frozen DTO or a plain mapping (T-Q271).
type AuditPayload = Mapping[str, object] | DataclassInstance


@dataclass(frozen=True, slots=True, kw_only=True)
class AuditEntry:
    """Append-only audit log row.

    `prev_json` / `new_json` are raw JSON strings; services parse on demand.
    """

    id: int
    entity_type: str
    entity_id: int
    changed_at: datetime
    operation: AuditOperation
    prev_json: str | None
    new_json: str | None
    user_id: int | None = None
    actor_user_id: int | None = None
