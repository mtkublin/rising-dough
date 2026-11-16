"""Remove the drill's leftover Tailscale node(s) after a drill destroy (T-D124, ADR-0101).

Destroying the drill VM leaves its tailnet node behind as offline. A later drill
would then register as `budget-planner-drill-1` and the `*.ts.net` certificate name
would not match. This script deletes every device that is named `budget-planner-drill`
or `budget-planner-drill-<n>` AND carries `tag:drill`.

Env: TS_CLEANUP_CLIENT_ID, TS_CLEANUP_SECRET (OAuth client, `devices:core` write,
tag:drill only). Stdlib only. Never prints the token or the secret. Always exits 0:
the VM is already gone, so any problem is a `::warning::`, never a failed job.
"""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from typing import Any

API = "https://api.tailscale.com/api/v2"
TIMEOUT_SECONDS = 30
DRILL_TAG = "tag:drill"
DRILL_HOSTNAME = re.compile(r"^budget-planner-drill(-[0-9]+)?$")


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


def _request(
    method: str, url: str, *, token: str | None = None, form: Mapping[str, str] | None = None
) -> Any:
    data = urllib.parse.urlencode(form).encode() if form is not None else None
    req = urllib.request.Request(url, data=data, method=method)  # noqa: S310
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


def cleanup(client_id: str, secret: str) -> int:
    """Return the number of failures (0 = clean or nothing to do)."""
    token = get_token(client_id, secret)
    devices = _request("GET", f"{API}/tailnet/-/devices", token=token).get("devices", [])
    targets = select_drill_devices(devices)
    if not targets:
        print("No drill tailnet node found; nothing to remove.")
        return 0
    failures = 0
    for device in targets:
        label = f"{_hostname(device)} ({device.get('id')})"
        try:
            _request("DELETE", f"{API}/device/{urllib.parse.quote(str(device['id']))}", token=token)
            print(f"Removed tailnet node {label}.")
        except (urllib.error.URLError, OSError, KeyError) as exc:
            failures += 1
            print(f"::warning::Could not remove tailnet node {label}: {type(exc).__name__}")
    return failures


def main(env: Mapping[str, str] | None = None) -> int:
    source = os.environ if env is None else env
    client_id = source.get("TS_CLEANUP_CLIENT_ID", "")
    secret = source.get("TS_CLEANUP_SECRET", "")
    if not client_id or not secret:
        print(
            "::warning::TS_CLEANUP_CLIENT_ID / TS_CLEANUP_SECRET not set; "
            "the drill tailnet node was not removed (remove it by hand, see runbooks/drill.md)."
        )
        return 0
    try:
        failures = cleanup(client_id, secret)
    except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
        print(f"::warning::Tailnet cleanup failed ({type(exc).__name__}); node may remain.")
        return 0
    if failures:
        print(f"::warning::{failures} drill tailnet node(s) could not be removed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
