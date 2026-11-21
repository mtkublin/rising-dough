#!/usr/bin/env python3
"""Diff the live Tailscale ACL against the runbook copy (T-Q238, OQ-24, Q-012).

Operator-run, read-only. The API token comes from the environment variable
``TAILSCALE_API_TOKEN`` (never committed, never printed). The runbook copy is
``docs/plans/v3/runbooks/tailscale-acl.hujson``; its placeholder owner
``you@example.com`` is replaced by ``--owner`` / ``TAILSCALE_OWNER_EMAIL``.

Usage: ``TAILSCALE_API_TOKEN=... uv run python scripts/tailscale_acl_drift.py --owner me@x.com``
Exit 0 = identical, 1 = drift, 2 = could not check.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

RUNBOOK_ACL = Path(__file__).resolve().parents[1] / "docs/plans/v3/runbooks/tailscale-acl.hujson"
PLACEHOLDER_OWNER = "you@example.com"
API_URL = "https://api.tailscale.com/api/v2/tailnet/-/acl"
TOKEN_ENV = "TAILSCALE_API_TOKEN"  # noqa: S105  # env var name, not a secret
OWNER_ENV = "TAILSCALE_OWNER_EMAIL"
TIMEOUT_S = 20

_TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/|,(?=\s*[}\]])', re.DOTALL)

Fetch = Callable[[str, str], bytes]


def parse_hujson(text: str) -> dict[str, Any]:
    """Parse JSON with comments and trailing commas (HuJSON) without a dependency."""

    def keep_strings(match: re.Match[str]) -> str:
        return match.group(0) if match.group(0).startswith('"') else ""

    doc = json.loads(_TOKEN.sub(keep_strings, text))
    if not isinstance(doc, dict):
        raise ValueError("ACL must be a JSON object")
    return doc


def _canon(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _canon(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return sorted((_canon(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    return value


def _dump(value: Any) -> str:
    return json.dumps(_canon(value), sort_keys=True)


def diff_acl(live: Mapping[str, Any], expected: Mapping[str, Any]) -> list[str]:
    """Human-readable drift lines; an empty list means identical (order-insensitive)."""
    drift: list[str] = []
    for key in sorted(set(live) - set(expected)):
        drift.append(f"{key}: present live, absent from the runbook copy")
    for key in sorted(set(expected) - set(live)):
        drift.append(f"{key}: in the runbook copy, absent live")
    for key in sorted(set(live) & set(expected)):
        if key == "acls":
            live_rules = {_dump(r) for r in live[key]}
            want_rules = {_dump(r) for r in expected[key]}
            drift += [f"acls: live-only rule {r}" for r in sorted(live_rules - want_rules)]
            drift += [f"acls: runbook-only rule {r}" for r in sorted(want_rules - live_rules)]
        elif _dump(live[key]) != _dump(expected[key]):
            drift.append(f"{key}: live {_dump(live[key])} != runbook {_dump(expected[key])}")
    return drift


def load_runbook_acl(path: Path, owner: str) -> dict[str, Any]:
    return parse_hujson(path.read_text().replace(PLACEHOLDER_OWNER, owner))


def fetch_live_acl(url: str, token: str) -> bytes:
    req = urllib.request.Request(  # noqa: S310  # https constant
        url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310  # https constant
        body: bytes = resp.read()
    return body


def compare_live(
    token: str, owner: str, runbook: Path = RUNBOOK_ACL, fetch: Fetch = fetch_live_acl
) -> list[str]:
    live = parse_hujson(fetch(API_URL, token).decode())
    return diff_acl(live, load_runbook_acl(runbook, owner))


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--owner", default=os.environ.get(OWNER_ENV, ""), help="your Tailscale login")
    args = ap.parse_args(argv)
    token = os.environ.get(TOKEN_ENV, "")
    if not token or not args.owner:
        print(f"set {TOKEN_ENV} and --owner (or {OWNER_ENV})", file=sys.stderr)
        return 2
    try:
        drift = compare_live(token, args.owner)
    except (OSError, ValueError) as exc:
        print(f"ACL check failed: {type(exc).__name__}", file=sys.stderr)  # never echo the token
        return 2
    print("\n".join(drift) if drift else "ACL matches the runbook copy")
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
