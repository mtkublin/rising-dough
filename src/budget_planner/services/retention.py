"""Personal-data retention purge (T-D60, ADR-0078 §7).

``audit_log.ip`` / ``user_agent`` are nulled and ended ``sessions`` rows are
deleted once older than ``Settings.retention_personal_days``. Idempotent;
counts only are logged (never the purged values).
"""

from __future__ import annotations

import datetime as dt
import sqlite3
from dataclasses import dataclass

from budget_planner.config import Settings
from budget_planner.logging import get_logger
from budget_planner.repositories import retention as repo

_ISO_FMT = "%Y-%m-%dT%H:%M:%S.%fZ"


@dataclass(frozen=True, slots=True)
class PurgeResult:
    audit_rows_scrubbed: int
    sessions_deleted: int


def cutoff(now: dt.datetime, retention_days: int) -> dt.datetime:
    """Rows strictly older than this instant are purged."""
    return now.astimezone(dt.UTC) - dt.timedelta(days=retention_days)


def purge(conn: sqlite3.Connection, now: dt.datetime, settings: Settings) -> PurgeResult:
    """Run the purge once and log ``retention_purge`` with counts only."""
    cutoff_iso = cutoff(now, settings.retention_personal_days).strftime(_ISO_FMT)
    result = PurgeResult(
        audit_rows_scrubbed=repo.scrub_audit_request_context(conn, cutoff_iso),
        sessions_deleted=repo.delete_ended_sessions(conn, cutoff_iso),
    )
    get_logger("budget_planner.retention").info(
        "retention_purge",
        audit_rows_scrubbed=result.audit_rows_scrubbed,
        sessions_deleted=result.sessions_deleted,
        retention_days=settings.retention_personal_days,
    )
    return result
