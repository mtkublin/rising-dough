"""Remove leftover Tailscale node(s) after a VM is destroyed (T-D124, ADR-0101; T-D156, ADR-0122).

Destroying a VM leaves its tailnet node behind as offline. The next VM would then
register as `<name>-1` (for the drill, the `*.ts.net` certificate name would not match).

`--env drill` (default): delete every device named `budget-planner-drill` or
`budget-planner-drill-<n>` AND carrying `tag:drill`.
`--env prod` (after a release that replaced the VM): delete only the OFFLINE devices
named `budget-planner-prod[-<n>]` with `tag:prod`, never an online one; then rename
the single online one to `budget-planner-prod` if it got a suffix.

Env: TS_CLEANUP_CLIENT_ID, TS_CLEANUP_SECRET (OAuth client, `devices:core` write,
tag:drill only for the drill, tag:prod only for prod). Stdlib only. Never prints the
token or the secret. Always exits 0: the old VM is already gone, so any problem is a
`::warning::`, never a failed job.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

API = "https://api.tailscale.com/api/v2"
TIMEOUT_SECONDS = 30
DRILL_TAG = "tag:drill"
DRILL_HOSTNAME = re.compile(r"^budget-planner-drill(-[0-9]+)?$")
PROD_TAG = "tag:prod"
PROD_NAME = "budget-planner-prod"
PROD_HOSTNAME = re.compile(r"^budget-planner-prod(-[0-9]+)?$")


def _hostname(device: Mapping[str, Any]) -> str:
    host = device.get("hostname")
    if isinstance(host, str) and host:
        return host
    name = device.get("name")
    return name.split(".", 1)[0] if isinstance(name, str) else ""


def is_drill_device(device: Mapping[str, Any]) -> bool:
    tags = device.get("tags") or []
    return DRILL_TAG in tags and DRILL_HOSTNAME.fullmatch(_hostname(device)) is not None


def select_drill_devices(devices: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [d for d in devices if is_drill_device(d)]


def _machine_name(device: Mapping[str, Any]) -> str:
    """First label of the MagicDNS name (carries the `-1` suffix); else the hostname."""
    name = device.get("name")
    if isinstance(name, str) and name:
        return name.split(".", 1)[0]
    return _hostname(device)


@dataclass(frozen=True)
class Replaced:
    """The tailnet name a replaced VM shares with its predecessor."""

    tag: str
    name: str

    def matches(self, device: Mapping[str, Any]) -> bool:
        pattern = re.compile(rf"^{re.escape(self.name)}(-[0-9]+)?$")
        tags = device.get("tags") or []
        return self.tag in tags and any(
            pattern.fullmatch(n) is not None for n in (_hostname(device), _machine_name(device))
        )


PROD = Replaced(PROD_TAG, PROD_NAME)


def created_at(device: Mapping[str, Any]) -> datetime | None:
    """The device's `created` time (RFC 3339), or None when missing or malformed."""
    value = device.get("created")
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def is_offline(device: Mapping[str, Any]) -> bool:
    """Only an explicit `connectedToControl: false` counts; unknown means keep it."""
    return device.get("connectedToControl") is False


def select_stale(devices: Sequence[Mapping[str, Any]], target: Replaced) -> list[Mapping[str, Any]]:
    return [d for d in devices if target.matches(d) and is_offline(d)]


def online_nodes(devices: Sequence[Mapping[str, Any]], target: Replaced) -> list[Mapping[str, Any]]:
    return [d for d in devices if target.matches(d) and not is_offline(d)]


def rename_target(
    devices: Sequence[Mapping[str, Any]], target: Replaced
) -> Mapping[str, Any] | None:
    """The single online node, when it does not already hold the plain name."""
    online = online_nodes(devices, target)
    if len(online) != 1 or _machine_name(online[0]) == target.name:
        return None
    return online[0]


def is_prod_device(device: Mapping[str, Any]) -> bool:
    return PROD.matches(device)


def select_stale_prod_devices(devices: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return select_stale(devices, PROD)


def prod_rename_target(devices: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    return rename_target(devices, PROD)


def _request(
    method: str,
    url: str,
    *,
    token: str | None = None,
    form: Mapping[str, str] | None = None,
    json_body: Mapping[str, str] | None = None,
) -> Any:
    if json_body is not None:
        data: bytes | None = json.dumps(json_body).encode()
    else:
        data = urllib.parse.urlencode(form).encode() if form is not None else None
    req = urllib.request.Request(url, data=data, method=method)  # noqa: S310
    if json_body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:  # noqa: S310
        body = resp.read()
    return json.loads(body) if body else {}


def get_token(client_id: str, secret: str) -> str:
    payload = _request(
        "POST",
        f"{API}/oauth/token",
        form={"client_id": client_id, "client_secret": secret, "grant_type": "client_credentials"},
    )
    return str(payload["access_token"])


def _delete(token: str, devices: Sequence[Mapping[str, Any]]) -> int:
    failures = 0
    for device in devices:
        label = f"{_machine_name(device)} ({device.get('id')})"
        try:
            _request("DELETE", f"{API}/device/{urllib.parse.quote(str(device['id']))}", token=token)
            print(f"Removed tailnet node {label}.")
        except (urllib.error.URLError, OSError, KeyError) as exc:
            failures += 1
            print(f"::warning::Could not remove tailnet node {label}: {type(exc).__name__}")
    return failures


def _rename(token: str, device: Mapping[str, Any], name: str) -> int:
    label = f"{_machine_name(device)} ({device.get('id')})"
    try:
        _request(
            "POST",
            f"{API}/device/{urllib.parse.quote(str(device['id']))}/name",
            token=token,
            json_body={"name": name},
        )
    except (urllib.error.URLError, OSError, KeyError) as exc:
        print(f"::warning::Could not rename tailnet node {label} to {name}: {type(exc).__name__}")
        return 1
    print(f"Renamed tailnet node {label} to {name}.")
    return 0


def _devices(client_id: str, secret: str) -> tuple[str, list[Mapping[str, Any]]]:
    token = get_token(client_id, secret)
    devices = _request("GET", f"{API}/tailnet/-/devices", token=token).get("devices", [])
    return token, devices


def cleanup(client_id: str, secret: str, env: str = "drill") -> int:
    """Return the number of failures (0 = clean or nothing to do)."""
    if env == "prod":
        return cleanup_replaced(client_id, secret, PROD)[0]
    token, devices = _devices(client_id, secret)
    targets = select_drill_devices(devices)
    if not targets:
        print("No drill tailnet node found; nothing to remove.")
        return 0
    return _delete(token, targets)


def cleanup_replaced(
    client_id: str, secret: str, target: Replaced, created_after: datetime | None = None
) -> tuple[int, bool]:
    """Delete offline `target` nodes, then give the online one the plain name.

    Returns (failures, settled). Settled: no failure and exactly one online node,
    now holding the plain name, and (with `created_after`) created after that
    time, so the old node can never count as the new one.
    """
    token, devices = _devices(client_id, secret)
    stale = select_stale(devices, target)
    failures = _delete(token, stale) if stale else 0
    if not stale:
        print(f"No offline {target.name} tailnet node found; nothing to remove.")
    online = online_nodes(devices, target)
    fresh = len(online) == 1 and _is_newer(online[0], created_after)
    node = rename_target(devices, target)
    if node is None:
        return failures, failures == 0 and fresh
    if failures:
        print(f"::warning::Not renaming {_machine_name(node)}: an old node is still there.")
        return failures + 1, False
    renamed = _rename(token, node, target.name)
    return renamed, renamed == 0 and fresh


def _is_newer(device: Mapping[str, Any], created_after: datetime | None) -> bool:
    if created_after is None:
        return True
    created = created_at(device)
    return created is not None and created > created_after


def main(env: Mapping[str, str] | None = None, argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", choices=("drill", "prod"), default="drill")
    parser.add_argument(
        "--replaced-name",
        default="",
        help="drill only (ADR-0122 §7): treat this drill name like prod after a VM replacement",
    )
    parser.add_argument(
        "--created-after",
        type=datetime.fromisoformat,
        default=None,
        help="with --require: the settled node must be created after this RFC 3339 time",
    )
    parser.add_argument(
        "--require",
        action="store_true",
        help="with --replaced-name: exit 1 until the name is settled (for a retry loop)",
    )
    args = parser.parse_args([] if argv is None and env is not None else argv)
    if args.replaced_name and (
        args.env != "drill" or not DRILL_HOSTNAME.fullmatch(args.replaced_name)
    ):
        parser.error("--replaced-name needs --env drill and a budget-planner-drill[-<n>] name")
    source = os.environ if env is None else env
    client_id = source.get("TS_CLEANUP_CLIENT_ID", "")
    secret = source.get("TS_CLEANUP_SECRET", "")
    if not client_id or not secret:
        print(
            "::warning::TS_CLEANUP_CLIENT_ID / TS_CLEANUP_SECRET not set; "
            f"the old {args.env} tailnet node was not removed "
            "(remove it by hand, see runbooks/drill.md or runbooks/deploy.md)."
        )
        return 1 if args.require else 0
    settled = True
    try:
        if args.replaced_name:
            failures, settled = cleanup_replaced(
                client_id, secret, Replaced(DRILL_TAG, args.replaced_name), args.created_after
            )
        else:
            failures = cleanup(client_id, secret, args.env)
    except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
        print(f"::warning::Tailnet cleanup failed ({type(exc).__name__}); node may remain.")
        return 1 if args.require else 0
    if args.require and not settled:
        print(f"{args.replaced_name}: not settled yet (old node online or rename pending).")
        return 1
    if failures:
        print(f"::warning::{failures} {args.env} tailnet node operation(s) failed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
