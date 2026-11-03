"""Read-only audit tail for the post-deploy smoke journey (T-D43).

Pure functions over :mod:`budget_planner.repositories.audit`. Secret-looking
keys are redacted defensively; existing audit payloads never carry them.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Final

from budget_planner.repositories import audit as audit_repo

DEFAULT_TAIL: Final = 20
MAX_TAIL: Final = 100
REDACTED: Final = "[redacted]"
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


def audit_tail(conn: sqlite3.Connection, n: int = DEFAULT_TAIL) -> list[dict[str, Any]]:
    """Latest ``n`` audit rows (newest first), ``n`` clamped to 1..MAX_TAIL."""
    limit = max(1, min(n, MAX_TAIL))
    return [
        {
            "id": e.id,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "changed_at": e.changed_at.isoformat(),
            "operation": e.operation.value,
            "prev": _parse(e.prev_json),
            "new": _parse(e.new_json),
        }
        for e in audit_repo.recent(conn, limit)
    ]


__all__ = ["DEFAULT_TAIL", "MAX_TAIL", "audit_tail"]
