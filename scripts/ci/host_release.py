"""Image refs and convergence wait for Terraform-declared host state (ADR-0111).

A release is one approved `terraform apply` that changes the image ref in the
host's instance metadata; the host agent converges within ~30 s. This script
holds the two CI-side rules, used by terraform.yml:

Subcommands (exit 0 = ok, 1 = refused / failed, message on stderr):
  refs --new REF --current REF --current-previous REF
       [--rollback] [--destroy] [--plan-only]
      Print `ref=...` and `previous=...` lines for $GITHUB_OUTPUT. Workflows
      pass them to Terraform steps as step-level `TF_VAR_app_image_ref` /
      `TF_VAR_app_image_previous_ref` (step env always wins over job env).
      `--current*` come from `terraform output` (empty before the first
      apply and after a destroy). Refs are
      `<tag>@sha256:<digest>`. A plan that is never applied (PR plan,
      -destroy) may fall back to a placeholder ref.
  resolve-ref --image IMAGE --tag TAG
      Resolve TAG of IMAGE (e.g. ghcr.io/owner/budget-planner) to its manifest
      digest with `docker buildx imagetools inspect` and print `ref=TAG@DIGEST`
      for $GITHUB_OUTPUT (T-D133). The caller logs in to the registry first.
  wait --url URL --generation GEN --ref FULL_REF [--timeout S] [--interval S]
       [--require-restore]
      Poll the agent status (/.well-known/bp-deploy-status.json) until it
      reports GEN applied and FULL_REF running; fail fast when the agent
      reports GEN failed. With --require-restore (a release that replaced the
      VM, T-D156 / ADR-0127) the status must also report
      `restore.result == "restored"`; any other value once converged fails.
  replaced
      Read `terraform show -json` plan output on stdin and print
      `replaced=true|false`: true when the plan deletes and recreates the app
      server (T-D156). When true, also print `server_id=<zone>/<uuid>`, the
      prior state's id of that server (the drain target, T-D157). The plan
      JSON holds secrets: nothing else of it is printed.
  wait-drained --url URL --request ID [--timeout S] [--interval S]
      Poll the agent status until it reports `state == "drained"` for drain
      request ID (T-D157, ADR-0127 amendment); fail fast on a `drain_*` failure.
  drain-capable --url URL [--timeout S] [--interval S]
      Fail unless the agent status carries a `drain` field, which every
      drain-capable agent publishes (`null` when idle). Run before the drain
      request is set (T-D158, ADR-0127 amendment 2).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess  # nosec B404
import sys
import time
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

REF = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}@sha256:[0-9a-f]{64}$")
# Valid ref for plans that are never applied (PR plan, -destroy) when state
# holds none; never reaches a host.
PLACEHOLDER = "sha-0000000@sha256:" + "0" * 64

# T-D156 / ADR-0127: the resource whose replacement means a fresh host + restore.
SERVER_ADDRESS = "module.compute.scaleway_instance_server.app"
RESTORED = "restored"
DRAINED = "drained"
SERVER_ID = re.compile(
    r"^[a-z]{2}-[a-z]{3}-[0-9]/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
DRAIN_REQUEST = re.compile(r"^[0-9A-Za-z._-]{1,64}$")

DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
TAG = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")

Fetch = Callable[[str], Mapping[str, object] | None]
Inspect = Callable[[str], str]


class ReleaseError(ValueError):
    """Raised when the refs cannot be resolved or the host did not converge."""


@dataclass(frozen=True)
class Refs:
    ref: str
    previous: str

    def output_lines(self) -> str:
        return f"ref={self.ref}\nprevious={self.previous}\n"


def _check(name: str, value: str) -> str:
    if value and not REF.fullmatch(value):
        raise ReleaseError(f"{name} must be <tag>@sha256:<64 hex>; got '{value}'")
    return value


def resolve_refs(
    new: str,
    current: str,
    current_previous: str,
    *,
    rollback: bool = False,
    destroy: bool = False,
    plan_only: bool = False,
) -> Refs:
    """Decide the refs for this plan. `current*` are read from state."""
    new = _check("new ref", new)
    current = _check("current ref", current)
    current_previous = _check("current previous ref", current_previous)
    if destroy:
        return Refs(current or new or PLACEHOLDER, "")
    if rollback:
        target = new or current_previous
        if not target:
            raise ReleaseError("rollback: no target given and state records no previous ref")
        if target == current:
            raise ReleaseError(f"rollback: host already runs {target}")
        return Refs(target, current)
    if new:
        previous = current if current and current != new else current_previous
        return Refs(new, previous)
    if current:
        return Refs(current, current_previous)
    if plan_only:
        return Refs(PLACEHOLDER, "")
    raise ReleaseError("no image ref: pass one, or apply once so state records it")


def resolve_ref(image: str, tag: str, inspect: Inspect) -> str:
    """`<tag>@<digest>` for `image:tag`; `inspect` returns the raw manifest digest."""
    if not TAG.fullmatch(tag):
        raise ReleaseError(f"image tag is not valid: '{tag}'")
    digest = inspect(f"{image}:{tag}").strip().strip('"')
    if not DIGEST.fullmatch(digest):
        raise ReleaseError(f"{image}:{tag} did not resolve to a sha256 digest; got '{digest}'")
    return _check("resolved ref", f"{tag}@{digest}")


def inspect_digest(image_tag: str) -> str:
    """Manifest digest of a registry image via buildx (needs a prior docker login)."""
    try:
        proc = subprocess.run(  # noqa: S603  # nosec B603 B607
            [  # noqa: S607
                "docker",
                "buildx",
                "imagetools",
                "inspect",
                image_tag,
                "--format",
                "{{json .Manifest.Digest}}",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReleaseError(f"cannot inspect {image_tag}: {exc}") from exc
    return proc.stdout


def converged(
    status: Mapping[str, object] | None,
    generation: str,
    ref: str,
    *,
    require_restore: bool = False,
) -> bool:
    """True when the agent reports `generation` applied and `ref` running.

    Raises ReleaseError when the agent reports this generation failed, or, with
    `require_restore`, when it converged without restoring the database.
    """
    if status is None or status.get("generation") != generation:
        return False
    if status.get("state") == "failed":
        raise ReleaseError(
            f"host failed to apply generation {generation[:12]}: {status.get('error')}"
        )
    done = status.get("state") == "ok" and status.get("running_ref") == ref
    if done and require_restore:
        restore = status.get("restore")
        result = restore.get("result") if isinstance(restore, Mapping) else None
        if result != RESTORED:
            raise ReleaseError(
                f"VM replaced but the host did not restore the database: restore={restore}"
            )
    return done


def server_replaced(plan: Mapping[str, object]) -> bool:
    """True when the plan deletes and recreates SERVER_ADDRESS (`terraform show -json`)."""
    changes = plan.get("resource_changes")
    if not isinstance(changes, list):
        raise ReleaseError("plan JSON has no resource_changes list")
    for change in changes:
        if not isinstance(change, Mapping) or change.get("address") != SERVER_ADDRESS:
            continue
        detail = change.get("change")
        actions = detail.get("actions") if isinstance(detail, Mapping) else None
        if not isinstance(actions, list):
            raise ReleaseError(f"{SERVER_ADDRESS}: plan has no actions list")
        return "delete" in actions and "create" in actions
    return False


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _resources(module: Mapping[str, object]) -> list[Mapping[str, object]]:
    found = [r for r in _list(module.get("resources")) if isinstance(r, Mapping)]
    for child in _list(module.get("child_modules")):
        if isinstance(child, Mapping):
            found.extend(_resources(child))
    return found


def prior_server_id(plan: Mapping[str, object]) -> str:
    """The prior state's id of SERVER_ADDRESS (`<zone>/<uuid>`); only that value is read."""
    prior = plan.get("prior_state")
    values = prior.get("values") if isinstance(prior, Mapping) else None
    root = values.get("root_module") if isinstance(values, Mapping) else None
    if not isinstance(root, Mapping):
        raise ReleaseError("plan JSON has no prior_state root module")
    for res in _resources(root):
        if res.get("address") != SERVER_ADDRESS:
            continue
        attrs = res.get("values")
        server_id = attrs.get("id") if isinstance(attrs, Mapping) else None
        if isinstance(server_id, str) and SERVER_ID.match(server_id):
            return server_id
        raise ReleaseError(f"{SERVER_ADDRESS}: prior state id is not <zone>/<uuid>")
    raise ReleaseError(f"{SERVER_ADDRESS} is not in the prior state")


def drained(status: Mapping[str, object] | None, request: str) -> bool:
    """True when the agent reports drain `request` done; raises on a drain failure."""
    if status is None:
        return False
    drain = status.get("drain")
    mine = isinstance(drain, Mapping) and drain.get("request") == request
    # Only this request's failure counts: a stale one from an earlier run must not.
    if (
        mine
        and status.get("state") == "failed"
        and str(status.get("error", "")).startswith("drain_")
    ):
        raise ReleaseError(f"host failed to drain: {status.get('error')}")
    return (
        status.get("state") == DRAINED
        and isinstance(drain, Mapping)
        and drain.get("request") == request
    )


def drain_capable(status: Mapping[str, object]) -> None:
    """Raise unless the agent publishes the `drain` field (T-D158)."""
    if "drain" not in status:
        raise ReleaseError(
            "host agent cannot drain (status has no `drain` field); "
            "release the agent in place first (ADR-0127 amendment 2)"
        )


def wait_status(
    fetch: Fetch,
    url: str,
    *,
    timeout: float,
    interval: float,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Mapping[str, object]:
    """The first status the host serves; raises when none comes within `timeout`."""
    deadline = clock() + timeout
    while True:
        status = fetch(url)
        if status is not None:
            return status
        if clock() >= deadline:
            raise ReleaseError(f"no host status within {timeout:.0f}s")
        sleep(interval)


def wait_drained(
    fetch: Fetch,
    url: str,
    request: str,
    *,
    timeout: float,
    interval: float,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Mapping[str, object]:
    if not DRAIN_REQUEST.match(request):
        raise ReleaseError(f"drain request id is not valid: '{request}'")
    deadline = clock() + timeout
    while True:
        last = fetch(url)
        if drained(last, request):
            return last if last is not None else {}
        if clock() >= deadline:
            raise ReleaseError(f"host did not drain within {timeout:.0f}s; last status: {last}")
        print(f"waiting for drain: {dict(last) if last else 'no status yet'}", file=sys.stderr)
        sleep(interval)


def read_plan(text: str) -> Mapping[str, object]:
    """Parse plan JSON without ever echoing it (it holds secrets)."""
    try:
        plan = json.loads(text)
    except ValueError:
        raise ReleaseError("stdin is not plan JSON (terraform show -json)") from None
    if not isinstance(plan, dict):
        raise ReleaseError("plan JSON is not an object")
    return plan


def wait_converged(
    fetch: Fetch,
    url: str,
    generation: str,
    ref: str,
    *,
    timeout: float,
    interval: float,
    require_restore: bool = False,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Mapping[str, object]:
    deadline = clock() + timeout
    last: Mapping[str, object] | None = None
    while True:
        last = fetch(url)
        if converged(last, generation, ref, require_restore=require_restore):
            return last if last is not None else {}
        if clock() >= deadline:
            raise ReleaseError(f"host did not converge within {timeout:.0f}s; last status: {last}")
        print(f"waiting: {dict(last) if last else 'no status yet'}", file=sys.stderr)
        sleep(interval)


def fetch_status(url: str) -> Mapping[str, object] | None:
    """GET the status JSON; None on any network or parse error (keep polling)."""
    if not url.startswith("https://"):
        raise ReleaseError(f"status url must be https; got '{url}'")
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:  # noqa: S310 (https enforced above)
            body = json.loads(resp.read())
    except (OSError, ValueError):
        return None
    return body if isinstance(body, dict) else None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    refs = sub.add_parser("refs")
    refs.add_argument("--new", default="")
    refs.add_argument("--current", default="")
    refs.add_argument("--current-previous", default="")
    refs.add_argument("--rollback", action="store_true")
    refs.add_argument("--destroy", action="store_true")
    refs.add_argument("--plan-only", action="store_true")
    resolve = sub.add_parser("resolve-ref")
    resolve.add_argument("--image", required=True)
    resolve.add_argument("--tag", required=True)
    wait = sub.add_parser("wait")
    wait.add_argument("--url", required=True)
    wait.add_argument("--generation", required=True)
    wait.add_argument("--ref", required=True)
    wait.add_argument("--timeout", type=float, default=600)
    wait.add_argument("--interval", type=float, default=10)
    wait.add_argument("--require-restore", action="store_true")
    sub.add_parser("replaced")
    drain = sub.add_parser("wait-drained")
    drain.add_argument("--url", required=True)
    drain.add_argument("--request", required=True)
    drain.add_argument("--timeout", type=float, default=300)
    drain.add_argument("--interval", type=float, default=5)
    capable = sub.add_parser("drain-capable")
    capable.add_argument("--url", required=True)
    capable.add_argument("--timeout", type=float, default=60)
    capable.add_argument("--interval", type=float, default=5)
    return parser


def main(
    argv: Sequence[str] | None = None,
    fetch: Fetch = fetch_status,
    inspect: Inspect = inspect_digest,
    stdin: Callable[[], str] = sys.stdin.read,
) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.cmd == "refs":
            resolved = resolve_refs(
                args.new,
                args.current,
                args.current_previous,
                rollback=args.rollback,
                destroy=args.destroy,
                plan_only=args.plan_only,
            )
            sys.stdout.write(resolved.output_lines())
        elif args.cmd == "resolve-ref":
            sys.stdout.write(f"ref={resolve_ref(args.image, args.tag, inspect)}\n")
        elif args.cmd == "replaced":
            plan = read_plan(stdin())
            replaced = server_replaced(plan)
            sys.stdout.write(f"replaced={'true' if replaced else 'false'}\n")
            if replaced:
                sys.stdout.write(f"server_id={prior_server_id(plan)}\n")
        elif args.cmd == "wait-drained":
            status = wait_drained(
                fetch, args.url, args.request, timeout=args.timeout, interval=args.interval
            )
            print(f"drained: {dict(status)}")
        elif args.cmd == "drain-capable":
            status = wait_status(fetch, args.url, timeout=args.timeout, interval=args.interval)
            drain_capable(status)
            print("host agent can drain")
        else:
            status = wait_converged(
                fetch,
                args.url,
                args.generation,
                args.ref,
                timeout=args.timeout,
                interval=args.interval,
                require_restore=args.require_restore,
            )
            print(f"converged: {dict(status)}")
    except ReleaseError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
