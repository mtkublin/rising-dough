"""Audit entry entity (ADR-0019)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from budget_planner.domain.enums import AuditOperation


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
