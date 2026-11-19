"""Set or delete the drain request key on a Scaleway instance (T-D157, ADR-0127 amendment).

A replacing release drains the old host first: CI sets the `user_data` key
`bp-drain` on the current server, the host agent stops the app and reports
`drained`, then the replacing apply runs. On a failed drain or apply CI deletes
the key and the agent starts the app again.

Only `bp-drain` can be touched: the other keys (`cloud-init`, `bp-agent`,
`bp-config`) are Terraform's. Stdlib only. The token comes from
$SCW_SECRET_KEY and is never printed.

Usage:
  scw_user_data.py set    --server <zone>/<uuid> --value <request id>
  scw_user_data.py delete --server <zone>/<uuid>     (404 = already gone: ok)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence

API = "https://api.scaleway.com/instance/v1"
KEY = "bp-drain"
SERVER_ID = re.compile(
    r"^(?P<zone>[a-z]{2}-[a-z]{3}-[0-9])/"
    r"(?P<uuid>[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$"
)
VALUE = re.compile(r"^[0-9A-Za-z._-]{1,64}$")
TIMEOUT_S = 30
HTTP_NOT_FOUND = 404

# (method, url, body, headers) -> HTTP status
Send = Callable[[str, str, bytes | None, Mapping[str, str]], int]


class UserDataError(Exception):
    pass


def key_url(server: str) -> str:
    match = SERVER_ID.match(server)
    if match is None:
        raise UserDataError(f"server must be <zone>/<uuid>; got '{server}'")
    return f"{API}/zones/{match['zone']}/servers/{match['uuid']}/user_data/{KEY}"


def send_request(method: str, url: str, body: bytes | None, headers: Mapping[str, str]) -> int:
    req = urllib.request.Request(url, data=body, method=method, headers=dict(headers))  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310 (fixed https API)
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except OSError as exc:
        raise UserDataError(f"{method} {KEY}: {type(exc).__name__}") from None


def set_key(server: str, value: str, token: str, send: Send = send_request) -> None:
    if not VALUE.match(value):
        raise UserDataError(f"value is not a valid request id: '{value}'")
    headers = {"X-Auth-Token": token, "Content-Type": "text/plain"}
    status = send("PATCH", key_url(server), value.encode(), headers)
    if status >= 300:  # noqa: PLR2004
        raise UserDataError(f"PATCH {KEY}: HTTP {status}")


def delete_key(server: str, token: str, send: Send = send_request) -> None:
    status = send("DELETE", key_url(server), None, {"X-Auth-Token": token})
    if status >= 300 and status != HTTP_NOT_FOUND:  # noqa: PLR2004
        raise UserDataError(f"DELETE {KEY}: HTTP {status}")


def main(
    argv: Sequence[str] | None = None,
    env: Mapping[str, str] = os.environ,
    send: Send = send_request,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    set_cmd = sub.add_parser("set")
    set_cmd.add_argument("--server", required=True)
    set_cmd.add_argument("--value", required=True)
    delete_cmd = sub.add_parser("delete")
    delete_cmd.add_argument("--server", required=True)
    args = parser.parse_args(argv)
    token = env.get("SCW_SECRET_KEY", "")
    try:
        if not token:
            raise UserDataError("SCW_SECRET_KEY is not set")
        if args.cmd == "set":
            set_key(args.server, args.value, token, send)
            print(f"set {KEY}={args.value} on {args.server}")
        else:
            delete_key(args.server, token, send)
            print(f"deleted {KEY} on {args.server}")
    except UserDataError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
