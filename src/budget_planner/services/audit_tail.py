"""Read-only audit tail for the post-deploy smoke journey (T-D43).

Pure functions over :mod:`budget_planner.repositories.audit`. Secret-looking
keys are redacted defensively; existing audit payloads never carry them.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Final

from budget_planner.domain.audit import AuditEntry
from budget_planner.repositories import audit as audit_repo

DEFAULT_TAIL: Final = 20
MAX_TAIL: Final = 100
REDACTED: Final = "[redacted]"
OTHER_USER: Final = "[other-user]"
_SECRET_MARKERS: Final = ("password", "secret", "token", "hash")


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: REDACTED if any(m in str(k).lower() for m in _SECRET_MARKERS) else _scrub(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def _parse(raw: str | None) -> Any:
    if raw is None:
        return None
    try:
        return _scrub(json.loads(raw))
    except json.JSONDecodeError:
        return REDACTED


def _is_own(e: AuditEntry, viewer_user_id: int) -> bool:
    if e.user_id is not None:
        return e.user_id == viewer_user_id
    return e.actor_user_id == viewer_user_id


def audit_tail(
    conn: sqlite3.Connection, viewer_user_id: int, n: int = DEFAULT_TAIL
) -> list[dict[str, Any]]:
    """Latest ``n`` audit rows (newest first), ``n`` clamped to 1..MAX_TAIL.

    Payloads are shown only for the viewer's own rows (ADR-0078 section 1,
    ADR-0061); other users' rows expose metadata and ``OTHER_USER``.
    """
    limit = max(1, min(n, MAX_TAIL))
    return [
        {
            "id": e.id,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "changed_at": e.changed_at.isoformat(),
            "operation": e.operation.value,
            "user_id": e.user_id,
            "prev": _parse(e.prev_json) if _is_own(e, viewer_user_id) else OTHER_USER,
            "new": _parse(e.new_json) if _is_own(e, viewer_user_id) else OTHER_USER,
        }
        for e in audit_repo.recent(conn, limit)
    ]


__all__ = ["DEFAULT_TAIL", "MAX_TAIL", "OTHER_USER", "audit_tail"]
