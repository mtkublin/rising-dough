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
  wait --url URL --generation GEN --ref FULL_REF [--timeout S] [--interval S]
      Poll the agent status (/.well-known/bp-deploy-status.json) until it
      reports GEN applied and FULL_REF running; fail fast when the agent
      reports GEN failed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

REF = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}@sha256:[0-9a-f]{64}$")
# Valid ref for plans that are never applied (PR plan, -destroy) when state
# holds none; never reaches a host.
PLACEHOLDER = "sha-0000000@sha256:" + "0" * 64

Fetch = Callable[[str], Mapping[str, object] | None]


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


def converged(status: Mapping[str, object] | None, generation: str, ref: str) -> bool:
    """True when the agent reports `generation` applied and `ref` running.

    Raises ReleaseError when the agent reports this generation failed.
    """
    if status is None or status.get("generation") != generation:
        return False
    if status.get("state") == "failed":
        raise ReleaseError(
            f"host failed to apply generation {generation[:12]}: {status.get('error')}"
        )
    return status.get("state") == "ok" and status.get("running_ref") == ref


def wait_converged(
    fetch: Fetch,
    url: str,
    generation: str,
    ref: str,
    *,
    timeout: float,
    interval: float,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Mapping[str, object]:
    deadline = clock() + timeout
    last: Mapping[str, object] | None = None
    while True:
        last = fetch(url)
        if converged(last, generation, ref):
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


def main(argv: Sequence[str] | None = None, fetch: Fetch = fetch_status) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    refs = sub.add_parser("refs")
    refs.add_argument("--new", default="")
    refs.add_argument("--current", default="")
    refs.add_argument("--current-previous", default="")
    refs.add_argument("--rollback", action="store_true")
    refs.add_argument("--destroy", action="store_true")
    refs.add_argument("--plan-only", action="store_true")
    wait = sub.add_parser("wait")
    wait.add_argument("--url", required=True)
    wait.add_argument("--generation", required=True)
    wait.add_argument("--ref", required=True)
    wait.add_argument("--timeout", type=float, default=600)
    wait.add_argument("--interval", type=float, default=10)
    args = parser.parse_args(argv)
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
        else:
            status = wait_converged(
                fetch,
                args.url,
                args.generation,
                args.ref,
                timeout=args.timeout,
                interval=args.interval,
            )
            print(f"converged: {dict(status)}")
    except ReleaseError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
