#!/usr/bin/env python3
"""GHCR image retention for budget-planner (T-D126, ADR-0099).

Keeps: newest KEEP_SHA `sha-...` versions, anything tagged `main` or `v*`, every
version younger than MIN_AGE_DAYS, the child manifests of every kept image index,
and cosign signature/attestation artifacts of kept images. Deletes the rest.
Never deletes unless --apply is passed; the default prints the plan only.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

KEEP_SHA = 20
MIN_AGE_DAYS = 7
PACKAGE = "budget-planner"
SIG_TAG = re.compile(r"^sha256-([0-9a-f]{64})\.(sig|att|sbom)$")
SHA_TAG = re.compile(r"^sha-[0-9a-f]+$")
RELEASE_TAG = re.compile(r"^(main|v\d.*)$")
INDEX_TYPES = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
)


@dataclass(frozen=True)
class Version:
    id: int
    digest: str
    created_at: datetime
    tags: tuple[str, ...]


@dataclass(frozen=True)
class Plan:
    keep: tuple[tuple[Version, str], ...]
    delete: tuple[tuple[Version, str], ...]


def parse_versions(raw: Sequence[Mapping[str, Any]]) -> list[Version]:
    return [
        Version(
            id=int(v["id"]),
            digest=str(v["name"]),
            created_at=datetime.fromisoformat(str(v["created_at"]).replace("Z", "+00:00")),
            tags=tuple(v.get("metadata", {}).get("container", {}).get("tags", [])),
        )
        for v in raw
    ]


def _classify_rest(v: Version, protected: set[str], keep_sha: int) -> tuple[bool, str]:
    """(delete?, reason) for a version that is old, not kept and not a protected child."""
    if not v.tags:
        return True, "untagged"
    if all(SIG_TAG.match(t) for t in v.tags):
        subjects = {f"sha256:{m.group(1)}" for t in v.tags if (m := SIG_TAG.match(t))}
        if subjects & protected:
            return False, "signature of a kept image"
        return True, "orphaned signature artifact"
    if all(SHA_TAG.match(t) for t in v.tags):
        return True, f"sha-* beyond newest {keep_sha}"
    return False, "unrecognised tag (kept, conservative)"


def select(
    versions: Sequence[Version],
    children: Mapping[str, Sequence[str]],
    now: datetime,
    keep_sha: int = KEEP_SHA,
    min_age_days: int = MIN_AGE_DAYS,
) -> Plan:
    """Pure selection. `children` maps an index digest to its child manifest digests."""
    cutoff = now - timedelta(days=min_age_days)
    sha_newest = sorted(
        (v for v in versions if any(SHA_TAG.match(t) for t in v.tags)),
        key=lambda v: v.created_at,
        reverse=True,
    )
    newest_ids = {v.id for v in sha_newest[:keep_sha]}

    reason: dict[int, str] = {}
    for v in versions:
        if any(RELEASE_TAG.match(t) for t in v.tags):
            reason[v.id] = "release tag (main or v*)"
        elif v.id in newest_ids:
            reason[v.id] = f"newest {keep_sha} sha-*"
        elif v.created_at > cutoff:
            reason[v.id] = f"younger than {min_age_days} days"

    protected = {v.digest for v in versions if v.id in reason}
    for digest in list(protected):
        protected.update(children.get(digest, ()))

    keep: list[tuple[Version, str]] = []
    delete: list[tuple[Version, str]] = []
    for v in sorted(versions, key=lambda v: v.created_at, reverse=True):
        if v.id in reason:
            keep.append((v, reason[v.id]))
        elif v.digest in protected:
            keep.append((v, "child manifest of a kept image"))
        else:
            is_delete, why = _classify_rest(v, protected, keep_sha)
            (delete if is_delete else keep).append((v, why))
    return Plan(keep=tuple(keep), delete=tuple(delete))


def _registry_token(owner: str, gh_token: str) -> str:
    basic = base64.b64encode(f"{owner}:{gh_token}".encode()).decode()
    url = f"https://ghcr.io/token?scope=repository:{owner}/{PACKAGE}:pull"
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {basic}"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310  # nosec B310
        return str(json.load(resp)["token"])


def fetch_children(owner: str, gh_token: str, digest: str, token: str | None = None) -> list[str]:
    """Child manifest digests of an image index (empty for a plain manifest)."""
    token = token or _registry_token(owner, gh_token)
    req = urllib.request.Request(
        f"https://ghcr.io/v2/{owner}/{PACKAGE}/manifests/{digest}",
        headers={"Authorization": f"Bearer {token}", "Accept": ", ".join(INDEX_TYPES)},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310  # nosec B310
        doc = json.load(resp)
    return [str(m["digest"]) for m in doc.get("manifests", [])]


def _gh(args: Sequence[str]) -> str:
    return subprocess.run(  # noqa: S603  # nosec B603
        ["gh", *args],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def list_versions(owner: str) -> list[Version]:
    out = _gh(
        [
            "api",
            "--paginate",
            "--slurp",
            f"/users/{owner}/packages/container/{PACKAGE}/versions?per_page=100",
        ]
    )
    pages = json.loads(out)
    return parse_versions([v for page in pages for v in page])


def format_plan(plan: Plan, apply: bool) -> str:
    lines = [f"mode: {'APPLY' if apply else 'DRY RUN (nothing is deleted)'}"]
    lines.append(f"keep: {len(plan.keep)} versions")
    for v, why in plan.keep:
        lines.append(f"  keep   {v.id} {v.digest[:19]} {','.join(v.tags) or '-'}  [{why}]")
    lines.append(f"delete: {len(plan.delete)} versions")
    for v, why in plan.delete:
        lines.append(f"  DELETE {v.id} {v.digest[:19]} {','.join(v.tags) or '-'}  [{why}]")
    return "\n".join(lines)


def main(argv: Sequence[str], clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--owner", required=True)
    ap.add_argument("--apply", action="store_true", help="really delete (default: plan only)")
    args = ap.parse_args(argv)
    gh_token = os.environ.get("GH_TOKEN", "")
    if not gh_token:
        print("GH_TOKEN is required", file=sys.stderr)
        return 1

    versions = list_versions(args.owner)
    if not versions:
        print("no versions found; refusing to continue", file=sys.stderr)
        return 1
    pre = select(versions, {}, clock())
    token = _registry_token(args.owner, gh_token)
    children = {
        v.digest: fetch_children(args.owner, gh_token, v.digest, token) for v, _ in pre.keep
    }
    plan = select(versions, children, clock())
    print(format_plan(plan, args.apply))
    if not plan.keep:
        print("selection kept nothing; refusing to delete", file=sys.stderr)
        return 1
    if not args.apply:
        return 0
    for v, _ in plan.delete:
        _gh(
            [
                "api",
                "-X",
                "DELETE",
                f"/users/{args.owner}/packages/container/{PACKAGE}/versions/{v.id}",
            ]
        )
        print(f"deleted {v.id}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
