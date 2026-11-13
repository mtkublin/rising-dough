"""SQLite connection factory.

Every connection returned here has:
- `foreign_keys` pragma ON (required for FK enforcement; per-connection).
- `journal_mode = WAL` for safer concurrent reads and required by Litestream.
- `synchronous = NORMAL` (safe with WAL).
- `wal_autocheckpoint = 0` — Litestream owns checkpoint cadence (ADR-0034 §2).
- `busy_timeout = 5000` ms — tolerates sidecar read bursts.
- `secure_delete = ON` — deleted/overwritten content is zeroed on disk
  instead of lingering in free pages (ADR-0078 §6).
- `row_factory = sqlite3.Row` for column-name access.
- `isolation_level = None` so transactions are managed explicitly.
- `check_same_thread = False` so a request-scoped connection can cross the
  anyio worker-thread boundary between a sync FastAPI dependency and the
  sync endpoint it feeds (see ADR-0029). Connections remain request-scoped
  and are never shared concurrently across threads.

Bypassing :func:`get_connection` to open a raw ``sqlite3.connect(...)`` is a
bug — Litestream requires ``wal_autocheckpoint = 0`` on every writer, see
ADR-0034 §2. Call this factory (or :func:`_apply_pragmas` on an existing
connection) instead.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from budget_planner.config import Settings

_SQLITE_PREFIX = "sqlite:///"


def _resolve_db_path(database_url: str) -> Path:
    if not database_url.startswith(_SQLITE_PREFIX):
        raise ValueError(f"Unsupported database_url (expected sqlite:///): {database_url!r}")
    return Path(database_url.removeprefix(_SQLITE_PREFIX))


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """Apply the Litestream-mandated PRAGMAs plus ``secure_delete`` on an existing connection.

    ``secure_delete`` (ADR-0078 §6) is a data-protection setting applied
    alongside the four Litestream PRAGMAs so that deleted rows are zeroed
    on disk rather than left readable in free pages.

    Separated from :func:`get_connection` so other factories (e.g. an
    in-memory test connection) can share the same invariant without
    duplicating the pragma list. ``foreign_keys`` is intentionally not set
    here — it is a correctness concern, not a durability concern, and lives
    with the connection factory itself.
    """
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA wal_autocheckpoint = 0;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    conn.execute("PRAGMA secure_delete = ON;")


def get_connection(settings: Settings) -> sqlite3.Connection:
    """Open a SQLite connection honouring project-wide pragmas.

    Creates the parent directory for the database file if missing.
    """
    db_path = _resolve_db_path(settings.database_url)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    # NOTE: we intentionally do NOT pass `detect_types`. All our TIMESTAMP
    # / DATE columns are stored as ISO-8601 strings and parsed manually in
    # the repository hydrators; sqlite3's built-in `convert_timestamp` is
    # deprecated in Python 3.12 (and emits warnings under `filterwarnings
    # = ["error"]`).
    conn = sqlite3.connect(db_path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    _apply_pragmas(conn)
    return conn
