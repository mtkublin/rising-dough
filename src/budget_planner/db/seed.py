"""Seed CLI entrypoint.

Static seed rows (default user, system categories) live in
``migrations/0003_seed_system_rows.sql``. Live demo rows that the UI needs
to render — such as the Phase 7 credit-card account (ADR-0024) — are
inserted here through the repository layer so audit discipline holds and
duplicates are avoided on re-seed.
"""

from __future__ import annotations

import sqlite3

from budget_planner.config import get_settings
from budget_planner.db.connection import get_connection
from budget_planner.db.migrate import apply_migrations
from budget_planner.domain.accounts import NewAccount
from budget_planner.repositories import accounts as accounts_repo


def _seed_demo_accounts(conn: sqlite3.Connection) -> None:
    """Idempotent demo accounts for the credit-card journey (T-086)."""
    if accounts_repo.find_by_name(conn, "Bank (PLN)") is None:
        accounts_repo.create(
            conn,
            NewAccount(
                name="Bank (PLN)",
                currency="PLN",
                opening_balance=5_000_000,
                type="bank",
            ),
        )
    if accounts_repo.find_by_name(conn, "Visa (PLN)") is None:
        accounts_repo.create(
            conn,
            NewAccount(
                name="Visa (PLN)",
                currency="PLN",
                opening_balance=0,
                type="credit_card",
                is_liability=True,
                credit_limit_minor=1_000_000,
            ),
        )


def seed(conn: sqlite3.Connection) -> None:
    """Apply migrations then write live demo rows. Idempotent."""
    apply_migrations(conn)
    _seed_demo_accounts(conn)


def main() -> None:  # pragma: no cover - CLI shim exercised via `just seed`
    settings = get_settings()
    conn = get_connection(settings)
    try:
        applied = apply_migrations(conn)
        for migration in applied:
            print(f"applied {migration.filename}")
        _seed_demo_accounts(conn)
    finally:
        conn.close()


if __name__ == "__main__":  # pragma: no cover
    main()
