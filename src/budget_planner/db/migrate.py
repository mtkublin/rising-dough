"""Hand-rolled numbered SQL migration runner.

Policy:
- Migration files are placed in ``migrations/`` and named ``NNNN_slug.sql``.
- Four-digit, zero-padded, strictly monotonic. No duplicates.
- Append-only: once applied, a migration's bytes are frozen (sha256 checked).
- No ``DROP TABLE`` in v1 against production data (table rebuilds inside a
  migration are allowed — the "no DROP" rule guards against destructive
  one-off cleanups, not against the SQLite 12-step rebuild pattern used by
  0007, 0008, and 0012).
- All migrations are applied against an existing connection managed by
  :func:`budget_planner.db.connection.get_connection`.
- Migrations that rebuild tables with incoming foreign keys must register
  their version in :data:`FK_OFF_MIGRATIONS` so the runner flips
  ``PRAGMA foreign_keys`` off for the duration of their SQL body.
- Companion ``migrations/down/NNNN_<slug>_down.sql`` scripts are
  forward-smoke-only — they exist to prove the forward migration is
  structurally reversible under CI, not to roll back production. See
  ``migrations/down/README.md``.

Public surface:
- :class:`Migration`
- :func:`discover`
- :func:`applied_versions`
- :func:`apply_migrations`
- :func:`main` (CLI entrypoint wired to ``just migrate``)
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from budget_planner.config import get_settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.enums import Cadence
from budget_planner.domain.recurring import RecurringRule
from budget_planner.services.recurring import generate_occurrences

MIGRATIONS_DIR: Path = Path(__file__).resolve().parents[3] / "migrations"
_FILENAME_RE = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


@dataclass(frozen=True, slots=True)
class Migration:
    """A single migration file loaded into memory."""

    version: int
    filename: str
    sql: str
    checksum: str


def discover(migrations_dir: Path = MIGRATIONS_DIR) -> list[Migration]:
    """Load all `.sql` migrations from `migrations_dir`, sorted ascending.

    Raises ``ValueError`` if a filename does not match ``NNNN_slug.sql`` or
    if versions are duplicate / non-monotonic.
    """
    files = sorted(p for p in migrations_dir.iterdir() if p.is_file() and p.suffix == ".sql")
    out: list[Migration] = []
    for p in files:
        match = _FILENAME_RE.match(p.name)
        if match is None:
            raise ValueError(f"Bad migration filename: {p.name}")
        body = p.read_bytes()
        out.append(
            Migration(
                version=int(match.group(1)),
                filename=p.name,
                sql=body.decode("utf-8"),
                checksum=hashlib.sha256(body).hexdigest(),
            )
        )
    versions = [m.version for m in out]
    if versions != sorted(set(versions)):
        raise ValueError("Duplicate or non-monotonic migration versions")
    return out


def _split_sql_statements(sql: str) -> list[str]:
    """Split a `.sql` migration file into individual statements.

    Strips `--` line comments, respects single/double-quoted strings, and
    tolerates stray whitespace / blank lines. Does not support `BEGIN`/`END`
    compound statements (triggers) — v1 schema has none.
    """
    out: list[str] = []
    buf: list[str] = []
    i = 0
    length = len(sql)
    in_single = False
    in_double = False
    while i < length:
        char = sql[i]
        # Line comments only when not inside a string literal.
        if not in_single and not in_double and char == "-" and i + 1 < length and sql[i + 1] == "-":
            while i < length and sql[i] != "\n":
                i += 1
            continue
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        if char == ";" and not in_single and not in_double:
            statement = "".join(buf).strip()
            if statement:
                out.append(statement)
            buf = []
            i += 1
            continue
        buf.append(char)
        i += 1
    trailing = "".join(buf).strip()
    if trailing:
        out.append(trailing)
    return out


def applied_versions(conn: sqlite3.Connection) -> dict[int, str]:
    """Return mapping of applied ``version -> checksum`` or ``{}`` on first run."""
    try:
        rows = conn.execute("SELECT version, checksum FROM schema_migrations").fetchall()
    except sqlite3.OperationalError:
        return {}
    return {int(r["version"]): r["checksum"] for r in rows}


def _backfill_recurring_next_due(conn: sqlite3.Connection) -> None:
    """Populate ``recurring_rules.next_due`` after migration 0006 applies.

    Runs idempotently in its own BEGIN/COMMIT: only rows whose ``next_due``
    is still ``NULL`` are touched. The schedule arithmetic reuses the pure
    ``services.recurring.generate_occurrences`` generator so canonical
    occurrence semantics (EOM clamp, yearly month-of-year roll-forward)
    stay in a single place. Rules whose ``end_date`` has already passed are
    deactivated and get ``next_due = start_date`` as a stable sentinel —
    the service layer ignores inactive rules anyway, so the sentinel never
    drives UI.
    """
    rows = conn.execute(
        "SELECT id, user_id, cadence, start_date, end_date, category_id, "
        "account_id, dest_account_id, default_amount, default_description, "
        "day_of_month, month_of_year, active "
        "FROM recurring_rules WHERE next_due IS NULL"
    ).fetchall()
    if not rows:
        return

    today = dt.date.today()  # noqa: DTZ011 — UTC vs local is irrelevant for a date-only anchor
    # 400 days covers monthly / quarterly / yearly in one shot — the first
    # canonical occurrence on-or-after `range_start` is at most one cadence
    # period away, and 400d > 366d.
    horizon_days = 400

    conn.execute("BEGIN")
    try:
        for row in rows:
            start_date = dt.date.fromisoformat(row["start_date"])
            end_date = (
                dt.date.fromisoformat(row["end_date"]) if row["end_date"] is not None else None
            )
            # Hydrate a minimal RecurringRule for the generator; the stub
            # satisfies the frozen dataclass but we force `active=True` so
            # the generator does not short-circuit for inactive rows — we
            # deactivate explicitly below when there is no occurrence left.
            rule = RecurringRule(
                id=row["id"],
                user_id=row["user_id"],
                cadence=Cadence(row["cadence"]),
                start_date=start_date,
                end_date=end_date,
                category_id=row["category_id"],
                account_id=row["account_id"],
                dest_account_id=row["dest_account_id"],
                default_amount=row["default_amount"],
                default_description=row["default_description"],
                day_of_month=row["day_of_month"],
                month_of_year=row["month_of_year"],
                active=True,
                next_due=start_date,  # placeholder; generator does not read it
                last_promoted_date=None,
                created_at=dt.datetime.now(dt.UTC),
                updated_at=dt.datetime.now(dt.UTC),
                deleted_at=None,
            )
            range_start = max(start_date, today)
            range_end = range_start + dt.timedelta(days=horizon_days)
            occurrences = generate_occurrences(rule, range_start, range_end)
            if occurrences:
                next_due = occurrences[0].occurrence_date
                conn.execute(
                    "UPDATE recurring_rules SET next_due = ? WHERE id = ?",
                    (next_due.isoformat(), row["id"]),
                )
            else:
                # Rule end has passed (or something equally terminal).
                # Sentinel + deactivation keeps the NOT NULL promise and
                # keeps the service layer honest.
                conn.execute(
                    "UPDATE recurring_rules SET next_due = ?, active = 0 WHERE id = ?",
                    (start_date.isoformat(), row["id"]),
                )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _upgrade_formula_schema_v1_to_v2(conn: sqlite3.Connection) -> None:
    """ADR-0047: transform v1 single-term `amount_formula` JSON to v2 terms list.

    v1 shape: ``{"coefficient_bps": X, "source_category_ids": [...]}``
    v2 shape: ``{"schema_version": 2, "terms": [{"sign": "+", ...}]}``

    Idempotent: rows already at ``schema_version == 2`` are left unchanged.
    """
    import json  # noqa: PLC0415 — hook-local import keeps top-of-module imports lean

    rows = conn.execute(
        "SELECT id, amount_formula FROM recurring_rules WHERE amount_formula IS NOT NULL"
    ).fetchall()
    conn.execute("BEGIN")
    try:
        for row in rows:
            raw = row["amount_formula"]
            data = json.loads(raw)
            if data.get("schema_version") == 2:  # noqa: PLR2004 — explicit version pin
                continue
            # v1 → v2 wrap. Single implicit "+" term carrying the v1 coefficient.
            v2 = {
                "schema_version": 2,
                "terms": [
                    {
                        "sign": "+",
                        "coefficient_bps": int(data["coefficient_bps"]),
                        "source_category_ids": [int(x) for x in data["source_category_ids"]],
                    }
                ],
            }
            conn.execute(
                "UPDATE recurring_rules SET amount_formula = ? WHERE id = ?",
                (json.dumps(v2, separators=(",", ":"), sort_keys=True), row["id"]),
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


# Mapping of migration version -> post-apply hook. Hooks run inside their
# own BEGIN/COMMIT after the migration's SQL commits, but strictly before
# any later migration runs. The sequence (0006 adds nullable column →
# backfill populates → 0007 flips to NOT NULL) hangs on this ordering.
_POST_APPLY_HOOKS: dict[int, Callable[[sqlite3.Connection], None]] = {
    6: _backfill_recurring_next_due,
    10: _upgrade_formula_schema_v1_to_v2,
}

# Migrations that require ``PRAGMA foreign_keys = OFF`` for the duration of
# their SQL body. Needed for SQLite's 12-step table-rebuild on tables with
# incoming foreign keys (ADR-0038 flips ``recurring_rules.next_due`` to
# NOT NULL at migration 0007; ``planned_transactions``, ``transactions``,
# and ``recurring_rule_overrides`` all reference ``recurring_rules.id``).
# Migration 0012 (ADR-0061) rebuilds every user-owned table at once to drop
# the ``DEFAULT 1`` sentinel on ``user_id`` — the FK pragma must stay off
# across the whole file because the rebuilt tables cross-reference each
# other (``transactions.account_id`` → ``accounts.id``, etc.).
# The pragma must flip OUTSIDE any transaction, so the toggle lives here
# rather than inside the SQL file. A post-rebuild ``PRAGMA foreign_key_check``
# fails fast if the rebuild dropped a reference.
FK_OFF_MIGRATIONS: frozenset[int] = frozenset({7, 8, 12})


def apply_migrations(
    conn: sqlite3.Connection,
    migrations_dir: Path = MIGRATIONS_DIR,
) -> list[Migration]:
    """Apply all pending migrations. Returns the list applied in this run.

    Behaviour:
    - Already-applied versions are skipped.
    - If an applied version's checksum differs from the file on disk, raises
      ``RuntimeError`` (editing applied migrations is forbidden).
    - Each pending migration runs inside its own ``BEGIN``/``COMMIT`` guard.
    - Migrations listed in :data:`FK_OFF_MIGRATIONS` run with
      ``PRAGMA foreign_keys = OFF`` for the duration of their SQL body
      (the pragma must flip outside the transaction). ``foreign_key_check``
      runs after the rebuild to surface any dangling references.
    - If ``_POST_APPLY_HOOKS`` registers a hook for a migration version,
      the hook runs AFTER the migration commits but BEFORE later migrations
      begin. Hooks must be idempotent (they are re-invoked on every
      ``just migrate`` run until the condition that makes them a no-op
      is satisfied; e.g. the ``next_due`` backfill checks for
      ``next_due IS NULL`` before writing).
    """
    all_migrations = discover(migrations_dir)
    applied = applied_versions(conn)
    newly_applied: list[Migration] = []
    for mig in all_migrations:
        if mig.version in applied:
            if applied[mig.version] != mig.checksum:
                raise RuntimeError(
                    f"Checksum mismatch for migration {mig.filename}: "
                    "already-applied migrations must not be edited."
                )
            continue
        fk_off = mig.version in FK_OFF_MIGRATIONS
        if fk_off:
            # Must be flipped outside any transaction; the runner has none
            # open at this point (prior migration committed).
            conn.execute("PRAGMA foreign_keys = OFF")
        # SQLite DDL is transactional. We avoid ``executescript`` (which
        # auto-commits any open transaction) by splitting the file into
        # individual statements and running each inside a single explicit
        # BEGIN/COMMIT so a failure anywhere rolls the whole thing back,
        # including the ``schema_migrations`` INSERT.
        conn.execute("BEGIN")
        try:
            for statement in _split_sql_statements(mig.sql):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations(version, filename, checksum) VALUES (?, ?, ?)",
                (mig.version, mig.filename, mig.checksum),
            )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            if fk_off:
                conn.execute("PRAGMA foreign_keys = ON")
            raise
        if fk_off:
            # Validate that the rebuild left no dangling foreign keys.
            offending = conn.execute("PRAGMA foreign_key_check").fetchall()
            if offending:
                conn.execute("PRAGMA foreign_keys = ON")
                raise RuntimeError(
                    f"Foreign-key check failed after migration {mig.filename}: "
                    f"{len(offending)} violation(s)."
                )
            conn.execute("PRAGMA foreign_keys = ON")
        newly_applied.append(mig)
        hook = _POST_APPLY_HOOKS.get(mig.version)
        if hook is not None:
            hook(conn)
    return newly_applied


def main() -> None:  # pragma: no cover - CLI shim exercised via `just migrate`
    """CLI entrypoint for ``python -m budget_planner.db.migrate``."""
    settings = get_settings()
    conn = get_connection(settings)
    try:
        applied = apply_migrations(conn)
        for migration in applied:
            print(f"applied {migration.filename}")
    finally:
        conn.close()


if __name__ == "__main__":  # pragma: no cover
    main()
