"""Replication freshness decision (T-D144, ADR-0119).

Pure functions: the ``litestream-probe`` sidecar writes a small JSON status
file (newest replica object time, generation, probe heartbeat); this module
turns its text into a verdict. Fail closed: anything unknown is not healthy.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

_logger = logging.getLogger(__name__)

#: The probe runs every 5 min; three missed runs mean the probe itself is down.
PROBE_MAX_AGE = timedelta(minutes=15)


@dataclass(frozen=True, slots=True, kw_only=True)
class ReplicationHealth:
    """Verdict for ``GET /health/replication``. ``ok`` maps to HTTP 200."""

    ok: bool
    status: str
    newest_object_at: str | None = None
    age_seconds: int | None = None
    max_age_seconds: int | None = None
    generation: str | None = None
    checked_at: str | None = None

    def body(self) -> dict[str, object]:
        return {
            "status": self.status,
            "newest_object_at": self.newest_object_at,
            "age_seconds": self.age_seconds,
            "max_age_seconds": self.max_age_seconds,
            "generation": self.generation,
            "checked_at": self.checked_at,
        }


def disabled() -> ReplicationHealth:
    """No status file configured (dev, prod-sim): nothing to check."""
    return ReplicationHealth(ok=True, status="disabled")


def read_status_text(path: str) -> str | None:
    """File content, or ``None`` when absent. Other IO errors propagate as OSError."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def evaluate(  # noqa: PLR0911 - one early return per failure state
    raw: str | None,
    *,
    now: datetime,
    max_age: timedelta,
    probe_max_age: timedelta = PROBE_MAX_AGE,
) -> ReplicationHealth:
    """Judge the probe status text. ``raw`` is ``None`` when the file is missing."""
    max_seconds = int(max_age.total_seconds())
    if raw is None:
        return ReplicationHealth(ok=False, status="missing", max_age_seconds=max_seconds)
    try:
        doc = json.loads(raw)
    except ValueError:
        doc = None
    if not isinstance(doc, dict):
        return ReplicationHealth(ok=False, status="unreadable", max_age_seconds=max_seconds)

    checked_at = _parse_time(doc.get("checked_at"))
    newest = _parse_time(doc.get("newest_object_at"))
    generation = _str_or_none(doc.get("generation"))
    checked_raw = _str_or_none(doc.get("checked_at"))
    newest_raw = _str_or_none(doc.get("newest_object_at"))

    def verdict(
        status: str, *, ok: bool = False, age_seconds: int | None = None
    ) -> ReplicationHealth:
        return ReplicationHealth(
            ok=ok,
            status=status,
            newest_object_at=newest_raw,
            age_seconds=age_seconds,
            max_age_seconds=max_seconds,
            generation=generation,
            checked_at=checked_raw,
        )

    if checked_at is None:
        return verdict("unreadable")
    if now - checked_at > probe_max_age:
        return verdict("probe_stale")
    if doc.get("error"):
        return verdict("probe_error")
    if newest is None:
        return verdict("no_objects")
    age = max(now - newest, timedelta(0))
    fresh = age <= max_age
    return verdict("ok" if fresh else "stale", ok=fresh, age_seconds=int(age.total_seconds()))


def check_status_file(
    status_file: str | None, *, max_age_hours: int, now: datetime
) -> ReplicationHealth:
    """Read the probe's status file (when configured) and decide freshness (ADR-0119)."""
    if not status_file:
        return disabled()
    try:
        raw = read_status_text(status_file)
    except OSError as exc:
        _logger.warning("replication_status_unreadable", exc_info=exc)
        raw = "unreadable"  # not JSON: evaluate() answers "unreadable"
    return evaluate(raw, now=now, max_age=timedelta(hours=max_age_hours))
