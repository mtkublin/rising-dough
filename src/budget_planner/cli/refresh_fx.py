"""Operator CLI: refresh cached FX rates from the live provider (ADR-0139).

Usage::

    python -m budget_planner.cli.refresh_fx --db=<path> --currency EUR --currency USD

Fetches ``<currency> -> base`` for today (display timezone) through the same
client factory the app uses (``adapters/fx``) and caches it. ``--db`` is
mandatory: there is deliberately no default database.

Exit codes: 0 all pairs cached, 1 at least one pair failed, 2 usage error.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

import httpx

from budget_planner import clock
from budget_planner.adapters.fx import frankfurter
from budget_planner.config import Settings
from budget_planner.db.connection import get_connection
from budget_planner.services import fx as fx_service


def _refresh_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="refresh_fx", description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="Path to the SQLite DB file.")
    parser.add_argument(
        "--currency", action="append", required=True, help="Source currency (repeatable)."
    )
    return parser


def main(argv: Sequence[str] | None = None, *, transport: httpx.BaseTransport | None = None) -> int:
    args = _refresh_parser().parse_args(argv)
    settings = Settings(_env_file=None, env="test", database_url=f"sqlite:///{args.db.as_posix()}")
    conn = get_connection(settings)
    try:
        with frankfurter.make_client(settings, transport=transport) as client:
            outcomes = fx_service.refresh_rates(
                conn,
                frankfurter.make_fetcher(client),
                clock.today_local(settings),
                settings.base_currency,
                args.currency,
            )
    finally:
        conn.close()
    for o in outcomes:
        status = f"rate {o.rate}" if o.error is None else f"FAILED: {o.error}"
        sys.stdout.write(f"{o.from_ccy}->{o.to_ccy}: {status}\n")
    return 1 if any(o.error is not None for o in outcomes) else 0


if __name__ == "__main__":
    sys.exit(main())
