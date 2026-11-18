"""Explicit drill lock: the first job of every drill workflow (T-D138, ADR-0115).

A drill VM is exclusive (ADR-0115). The shared concurrency group `drill` only
serialises RUNS; it does not know that a kept explore drill outlives its run, and
it silently drops a pending run when a newer one arrives. This script fails the
run, with an explicit `::error::`, when something already holds the drill:

  a. another drill-group workflow run is active (GitHub API, `actions: read`);
  b. a drill VM exists (ground truth: Scaleway drill project, servers named
     `budget-planner-drill*`);
  c. an online `tag:drill` node `budget-planner-drill[-n]` exists in the tailnet
     (read-only cross-check, same OAuth client as `tailnet_drill_cleanup.py`).

Env:
  GITHUB_TOKEN, GITHUB_REPOSITORY, GITHUB_RUN_ID   (a)
  DRILL_LOCK_FORCE      "true" skips b and c (never a); operator-only, loud warning
  DRILL_LOCK_CHECK_VM   "false" skips b and c (drill-destroy / sweeper: they are
                        how the VM is cleared); default "true"
  SCW_SECRET_KEY, SCW_DEFAULT_PROJECT_ID, [SCW_ZONE]   (b)
  TS_CLEANUP_CLIENT_ID, TS_CLEANUP_SECRET              (c)

Every API error fails closed (exit 2). Exit 0 = lock acquired, 1 = held. Stdlib only;
the tailnet helpers are reused from `scripts/tailnet_drill_cleanup.py`. Never prints
a token or secret.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

GITHUB_API = "https://api.github.com"
SCW_API = "https://api.scaleway.com/instance/v1"
DEFAULT_ZONE = "pl-waw-2"
SERVER_PREFIX = "budget-planner-drill"
EXPIRES_TAG = "expires-at="
TIMEOUT_SECONDS = 30
DRILL_WORKFLOWS = frozenset(
    {
        "drill.yml",
        "restore-drill.yml",
        "drill-destroy.yml",
        "drill-sweeper.yml",
        "rollback.yml",
    }
)
# GitHub run statuses that mean "bringing up or running".
ACTIVE_STATUSES = ("queued", "in_progress", "waiting", "pending")
# Statuses of a run that may merely be queued BEHIND this run in the `drill` group.
BEHIND_STATUSES = frozenset({"queued", "pending"})

EXIT_OK = 0
EXIT_HELD = 1
EXIT_ERROR = 2

Getter = Callable[[str, Mapping[str, str]], Any]


class LockError(Exception):
    """An API call failed; the lock cannot be evaluated (fail closed)."""


def _parse_time(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _http_get(url: str, headers: Mapping[str, str]) -> Any:
    req = urllib.request.Request(url, headers=dict(headers), method="GET")  # noqa: S310
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:  # noqa: S310
            body = resp.read()
    except urllib.error.HTTPError as exc:
        raise LockError(f"GET {url.split('?', maxsplit=1)[0]} failed: HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise LockError(
            f"GET {url.split('?', maxsplit=1)[0]} failed: {type(exc).__name__}"
        ) from exc
    try:
        return json.loads(body) if body else {}
    except ValueError as exc:
        raise LockError(f"GET {url.split('?', maxsplit=1)[0]} returned invalid JSON") from exc


# --- a. other drill-group runs -------------------------------------------------------


def _workflow_file(run: Mapping[str, Any]) -> str:
    path = str(run.get("path") or "")
    return path.split("@", 1)[0].rsplit("/", 1)[-1]


def _is_prod_rollback(run: Mapping[str, Any]) -> bool:
    """rollback.yml sets run-name `rollback (<env>)`; only an explicit prod run is skipped."""
    title = str(run.get("display_title") or run.get("name") or "").lower()
    return title.startswith("rollback (prod")


def evaluate_runs(
    runs: Sequence[Mapping[str, Any]], *, own_run_id: int, own_created_at: datetime | None
) -> list[str]:
    """Findings for other active drill-group runs.

    A run that is `queued`/`pending` and was created AFTER this one is waiting in the
    `drill` concurrency group behind us, so it is not a holder. `in_progress` and
    `waiting` always count (a waiting run holds the group while approval is pending).
    """
    findings: list[str] = []
    for run in runs:
        if run.get("id") == own_run_id or _workflow_file(run) not in DRILL_WORKFLOWS:
            continue
        if _workflow_file(run) == "rollback.yml" and _is_prod_rollback(run):
            continue
        status = str(run.get("status"))
        created = _parse_time(str(run.get("created_at") or ""))
        queued_behind = (
            status in BEHIND_STATUSES
            and own_created_at is not None
            and created is not None
            and created > own_created_at
        )
        if queued_behind:
            continue
        findings.append(
            f"another drill run is active: workflow '{run.get('name')}' run {run.get('id')} "
            f"({status}) {run.get('html_url')}; wait for it or cancel it"
        )
    return findings


def check_runs(env: Mapping[str, str], get: Getter) -> list[str]:
    token = env.get("GITHUB_TOKEN", "")
    repo = env.get("GITHUB_REPOSITORY", "")
    run_id_text = env.get("GITHUB_RUN_ID", "")
    if not token or not repo or not run_id_text.isdigit():
        raise LockError("GITHUB_TOKEN, GITHUB_REPOSITORY and GITHUB_RUN_ID must be set")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    own = get(f"{GITHUB_API}/repos/{repo}/actions/runs/{run_id_text}", headers)
    own_created = _parse_time(str(own.get("created_at") or ""))
    seen: dict[int, Mapping[str, Any]] = {}
    for status in ACTIVE_STATUSES:
        url = f"{GITHUB_API}/repos/{repo}/actions/runs?status={status}&per_page=100"
        for run in get(url, headers).get("workflow_runs", []):
            seen[int(run["id"])] = run
    return evaluate_runs(
        list(seen.values()), own_run_id=int(run_id_text), own_created_at=own_created
    )


# --- b. Scaleway drill VM --------------------------------------------------------------


def _expires_tag(server: Mapping[str, Any]) -> str:
    for tag in server.get("tags") or []:
        if str(tag).startswith(EXPIRES_TAG):
            return str(tag)[len(EXPIRES_TAG) :]
    return ""


def evaluate_servers(servers: Sequence[Mapping[str, Any]], *, now: datetime) -> list[str]:
    findings: list[str] = []
    for server in servers:
        name = str(server.get("name") or "")
        if not name.startswith(SERVER_PREFIX):
            continue
        expires = _expires_tag(server)
        created = server.get("creation_date") or "unknown"
        expires_at = _parse_time(expires) if expires else None
        if expires_at is not None and expires_at <= now:
            findings.append(
                f"expired drill still up: VM {name} expired at {expires} (created {created}), "
                "the sweeper has not run yet; run drill-destroy.yml first"
            )
        elif expires_at is not None:
            findings.append(
                f"drill VM {name} is up until {expires} (created {created}) "
                "(kept explore drill?); run drill-destroy.yml or wait"
            )
        else:
            findings.append(
                f"drill VM {name} is up with no usable expires-at tag (created {created}); "
                "run drill-destroy.yml first"
            )
    return findings


def check_servers(env: Mapping[str, str], get: Getter, now: datetime) -> list[str]:
    secret = env.get("SCW_SECRET_KEY", "")
    project = env.get("SCW_DEFAULT_PROJECT_ID", "")
    if not secret or not project:
        raise LockError("SCW_SECRET_KEY and SCW_DEFAULT_PROJECT_ID must be set to list drill VMs")
    zone = env.get("SCW_ZONE") or DEFAULT_ZONE
    url = f"{SCW_API}/zones/{zone}/servers?project={project}&per_page=100"
    payload = get(url, {"X-Auth-Token": secret})
    return evaluate_servers(payload.get("servers", []), now=now)


# --- c. tailnet cross-check --------------------------------------------------------------


def _load_cleanup() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "tailnet_drill_cleanup.py"
    spec = importlib.util.spec_from_file_location("tailnet_drill_cleanup", path)
    if spec is None or spec.loader is None:
        raise LockError(f"cannot load {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def evaluate_devices(devices: Sequence[Mapping[str, Any]], cleanup: ModuleType) -> list[str]:
    findings: list[str] = []
    for device in cleanup.select_drill_devices(devices):
        if device.get("connectedToControl") is not True:
            continue  # offline leftover: tailnet_drill_cleanup.py removes it, not a holder
        findings.append(
            f"tailnet node {cleanup._hostname(device)} (tag:drill) is online; "
            "a drill VM is running; run drill-destroy.yml or wait"
        )
    return findings


def check_tailnet(env: Mapping[str, str]) -> list[str]:
    client_id = env.get("TS_CLEANUP_CLIENT_ID", "")
    secret = env.get("TS_CLEANUP_SECRET", "")
    if not client_id or not secret:
        raise LockError(
            "TS_CLEANUP_CLIENT_ID and TS_CLEANUP_SECRET must be set for the tailnet check"
        )
    cleanup = _load_cleanup()
    try:
        token = cleanup.get_token(client_id, secret)
        devices = cleanup._request("GET", f"{cleanup.API}/tailnet/-/devices", token=token)
    except (urllib.error.URLError, OSError, KeyError, ValueError) as exc:
        raise LockError(f"tailnet device listing failed: {type(exc).__name__}") from exc
    return evaluate_devices(devices.get("devices", []), cleanup)


# --- orchestration -----------------------------------------------------------------------


def _truthy(value: str | None, *, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() == "true"


def acquire(
    env: Mapping[str, str],
    *,
    get: Getter = _http_get,
    now: datetime | None = None,
    tailnet_check: Callable[[Mapping[str, str]], list[str]] = check_tailnet,
) -> tuple[int, list[str]]:
    """Return (exit code, lines to print). Lines starting with `::` are workflow commands."""
    current = now or datetime.now(UTC)
    force = _truthy(env.get("DRILL_LOCK_FORCE"), default=False)
    check_vm = _truthy(env.get("DRILL_LOCK_CHECK_VM"), default=True)
    out: list[str] = []
    try:
        findings = check_runs(env, get)
        if check_vm and force:
            out.append(
                "::warning::FORCE: drill lock checks b/c (drill VM, tailnet node) are SKIPPED. "
                "This can replace and destroy a running explore drill. Operator-only."
            )
        elif check_vm:
            findings = [
                *findings,
                *check_servers(env, get, current),
                *tailnet_check(env),
            ]
    except LockError as exc:
        return EXIT_ERROR, [f"::error::drill lock cannot be evaluated (failing closed): {exc}"]
    if findings:
        return EXIT_HELD, [*out, *(f"::error::drill lock held: {f}" for f in findings)]
    if not check_vm:
        out.append("drill lock acquired: no other drill run (VM check not required here)")
    elif force:
        out.append("drill lock acquired (force): no other drill run; VM checks skipped")
    else:
        out.append("drill lock acquired: no drill VM, no other drill run")
    return EXIT_OK, out


def main(env: Mapping[str, str] | None = None) -> int:
    code, lines = acquire(os.environ if env is None else env)
    for line in lines:
        print(line)
    return code


if __name__ == "__main__":
    sys.exit(main())
