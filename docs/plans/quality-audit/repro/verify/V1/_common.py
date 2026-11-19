"""Shared helper: fresh scratch copy of demo.sqlite, migrated (COPY only).

Never touches data/budget.sqlite. Run scripts from this directory with
the project venv python.
"""

from __future__ import annotations

import shutil
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[6]
sys.path.insert(0, str(REPO / "src"))
SCRATCH = Path("/tmp/verify-V1.sqlite")
USER_ID = 1


def fresh_conn() -> sqlite3.Connection:
    from budget_planner.config import Settings
    from budget_planner.db.connection import get_connection
    from budget_planner.db.migrate import apply_migrations

    for suf in ("", "-wal", "-shm"):
        p = Path(str(SCRATCH) + suf)
        if p.exists():
            p.unlink()
    shutil.copyfile(REPO / "data" / "demo.sqlite", SCRATCH)
    s = Settings(_env_file=None, database_url=f"sqlite:///{SCRATCH.as_posix()}")
    conn = get_connection(s)
    apply_migrations(conn)
    return conn
