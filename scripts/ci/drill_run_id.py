"""Pick the drill run id for an apply on an EXISTING drill (T-D139, ADR-0116).

Only the run that creates the drill VM may mint a new `drill_run_id` (its own
run id). A later apply on the same state (rollback.yml env=drill) must keep the
id the host name was built from, or the host agent rewrites the hostname and
Caddy loses its tailscale certificate.

Precedence: explicit override (operator repair path), else the value recorded in
Terraform state (`terraform output -raw drill_run_id`). Neither, or a value that
is not digits only, is an error: there is never a fallback to a new id.

Usage: python3 drill_run_id.py --override "<digits or empty>" --state "<output>"
Prints the id on stdout.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence

_DIGITS = re.compile(r"[0-9]{1,20}")


class DrillRunIdError(ValueError):
    """No usable drill run id."""


def resolve(override: str, state: str) -> str:
    """Return the id to reuse: `override` if set, else `state`; digits only."""
    override, state = override.strip(), state.strip()
    for label, value in (("drill_run_id input", override), ("state drill_run_id", state)):
        if value and not _DIGITS.fullmatch(value):
            raise DrillRunIdError(f"{label} must be digits only; got '{value}'")
    chosen = override or state
    if not chosen:
        raise DrillRunIdError(
            "no drill run id in state and no drill_run_id input; refusing to mint a new one "
            "(it would rename the drill host). Is there a live drill?"
        )
    return chosen


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--override", default="")
    parser.add_argument("--state", default="")
    args = parser.parse_args(argv)
    try:
        print(resolve(args.override, args.state))
    except DrillRunIdError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
