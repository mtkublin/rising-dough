"""``python -m budget_planner.db.retention`` — one-shot retention purge (T-D60).

Run by the container entrypoint after ``startup_migrate``. Non-fatal by
design: any failure is logged and the process exits 1 (the entrypoint
ignores it so the app still starts).
"""

from __future__ import annotations

import datetime as dt

from budget_planner import logging as bp_logging
from budget_planner.config import Settings, get_settings
from budget_planner.db.connection import get_connection
from budget_planner.services import retention


def run(settings: Settings) -> retention.PurgeResult:
    conn = get_connection(settings)
    try:
        return retention.purge(conn, dt.datetime.now(dt.UTC), settings)
    finally:
        conn.close()


def main(settings: Settings | None = None) -> int:
    bp_logging.configure()
    log = bp_logging.get_logger("budget_planner.retention")
    try:
        run(settings or get_settings())
    except Exception as exc:  # non-fatal for startup; report via exit code
        log.error("retention_purge_failed", error=str(exc), error_type=type(exc).__name__)
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover — exercised via the entrypoint
    raise SystemExit(main())
