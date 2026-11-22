"""Operator CLI: refresh cached FX rates from NBP table A (ADR-0145).

Usage::

    python -m budget_planner.cli.refresh_fx --db=<path> [--currency EUR --currency USD]

Runs the same ``services.fx.refresh_from_source`` as the daily in-app task and
caches the latest table under its effective date. ``--currency`` restricts the
stored currencies (default: every known code in the table). ``--db`` is
mandatory: there is deliberately no default database.

Exit codes: 0 refreshed (or no new data), 1 the provider failed, 2 usage error.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import httpx

from budget_planner import clock
from budget_planner.adapters.fx import nbp
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.domain.fx import FxFetchError
from budget_planner.services import fx as fx_service


def _refresh_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="refresh_fx", description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="Path to the SQLite DB file.")
    parser.add_argument(
        "--currency", action="append", default=None, help="Only store this currency (repeatable)."
    )
    return parser


def main(argv: Sequence[str] | None = None, *, transport: httpx.BaseTransport | None = None) -> int:
    args = _refresh_parser().parse_args(argv)
    settings = Settings(_env_file=None, env="test", database_url=f"sqlite:///{args.db.as_posix()}")
    conn = get_connection(settings)
    try:
        with nbp.make_client(settings, transport=transport) as client:
            result = fx_service.refresh_from_source(
                conn,
                nbp.NbpRateSource(client),
                clock.today_local(settings),
                settings.base_currency,
                args.currency,
            )
    except FxFetchError as exc:
        sys.stdout.write(f"FAILED: {exc}\n")
        return 1
    finally:
        conn.close()
    if result is None:
        sys.stdout.write("no data from NBP; cache unchanged\n")
        return 0
    sys.stdout.write(
        f"{result.effective_date}: inserted {len(result.inserted)}, "
        f"updated {len(result.updated)}, unchanged {len(result.unchanged)}\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
