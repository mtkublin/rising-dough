"""Resolve the version prod serves: the baseline of the upgrade drill gate (T-Q306a, ADR-0149).

Picks the newest deployment to the GitHub `prod` environment whose LATEST status is
`success`; its `ref` is the release tag. A tag that was pushed but never deployed
(v3.1.1) has no successful deployment and is skipped. The tag must be an ancestor
of `origin/main`, and `<image>:<tag>` must resolve to a manifest digest (the same
`docker buildx imagetools inspect` path as `host_release.py resolve-ref`; the
caller logs in to GHCR first).

Usage:
  prod_baseline.py [--repo OWNER/NAME] [--image IMAGE] [--main-ref origin/main]

Prints (and appends to $GITHUB_OUTPUT when set) `tag=`, `sha=` and
`image_ref=<image>:<tag>@sha256:<digest>`. Any failure exits 1 with a message on
stderr (fail closed).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess  # nosec B404
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import host_release

ENVIRONMENT = "prod"
SUCCESS = "success"
PAGE_SIZE = 30

# (path) -> parsed JSON; the edge that talks to the GitHub API.
Api = Callable[[str], object]
IsAncestor = Callable[[str], bool]


class BaselineError(Exception):
    """The prod baseline cannot be resolved; the gate must not run."""


@dataclass(frozen=True)
class Baseline:
    tag: str
    sha: str
    image_ref: str

    def output_lines(self) -> str:
        return f"tag={self.tag}\nsha={self.sha}\nimage_ref={self.image_ref}\n"


def _latest_state(statuses: object) -> str:
    """State of the newest status (the API lists newest first); '' when none."""
    if not isinstance(statuses, list) or not statuses:
        return ""
    first = statuses[0]
    state = first.get("state") if isinstance(first, Mapping) else None
    return state if isinstance(state, str) else ""


def select_deployment(
    deployments: object, statuses_for: Callable[[int], object]
) -> Mapping[str, object]:
    """Newest deployment (list is newest first) whose latest status is `success`."""
    if not isinstance(deployments, list):
        raise BaselineError("deployments response is not a list")
    for item in deployments:
        if not isinstance(item, Mapping):
            continue
        dep_id = item.get("id")
        if isinstance(dep_id, int) and _latest_state(statuses_for(dep_id)) == SUCCESS:
            return item
    raise BaselineError(f"no successful deployment to the '{ENVIRONMENT}' environment")


def resolve_baseline(
    deployments: object,
    statuses_for: Callable[[int], object],
    *,
    image: str,
    main_ref: str,
    is_ancestor: IsAncestor,
    inspect: host_release.Inspect,
) -> Baseline:
    """Pure selection; every effect is injected."""
    chosen = select_deployment(deployments, statuses_for)
    tag = chosen.get("ref")
    sha = chosen.get("sha")
    if not isinstance(tag, str) or not tag or not isinstance(sha, str) or not sha:
        raise BaselineError(f"deployment {chosen.get('id')} has no ref or sha")
    if not is_ancestor(tag):
        raise BaselineError(f"prod tag {tag} is not an ancestor of {main_ref}")
    try:
        ref = host_release.resolve_ref(image, tag, inspect)
    except host_release.ReleaseError as exc:
        raise BaselineError(f"cannot resolve image digest for {image}:{tag}: {exc}") from exc
    return Baseline(tag=tag, sha=sha, image_ref=f"{image}:{ref}")


def gh_api(path: str) -> object:
    """GET `path` through the gh CLI (uses GH_TOKEN) and parse the JSON."""
    try:
        proc = subprocess.run(  # noqa: S603  # nosec B603 B607
            ["gh", "api", path],  # noqa: S607
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(proc.stdout)
    except (OSError, subprocess.CalledProcessError, ValueError) as exc:
        raise BaselineError(f"gh api {path} failed: {exc}") from exc


def git_is_ancestor(tag: str, main_ref: str) -> bool:
    """True when `tag` is an ancestor of `main_ref`; False when it is not or is missing."""
    proc = subprocess.run(  # noqa: S603  # nosec B603 B607
        ["git", "merge-base", "--is-ancestor", f"refs/tags/{tag}^{{commit}}", main_ref],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Resolve the prod baseline for the upgrade drill.")
    p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    p.add_argument("--image", default="")
    p.add_argument("--main-ref", default="origin/main")
    return p


def main(
    argv: Sequence[str] | None = None,
    api: Api = gh_api,
    is_ancestor: Callable[[str, str], bool] = git_is_ancestor,
    inspect: host_release.Inspect = host_release.inspect_digest,
) -> int:
    args = _parser().parse_args(argv)
    try:
        repo: str = args.repo
        if "/" not in repo:
            raise BaselineError("--repo OWNER/NAME (or $GITHUB_REPOSITORY) is required")
        image = args.image or f"ghcr.io/{repo.split('/', maxsplit=1)[0].lower()}/budget-planner"
        deployments = api(
            f"repos/{repo}/deployments?environment={ENVIRONMENT}&per_page={PAGE_SIZE}"
        )
        baseline = resolve_baseline(
            deployments,
            lambda dep_id: api(f"repos/{repo}/deployments/{dep_id}/statuses?per_page=1"),
            image=image,
            main_ref=args.main_ref,
            is_ancestor=lambda tag: is_ancestor(tag, args.main_ref),
            inspect=inspect,
        )
    except BaselineError as exc:
        print(f"prod_baseline: {exc}", file=sys.stderr)
        return 1
    out = baseline.output_lines()
    sys.stdout.write(out)
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with Path(target).open("a", encoding="utf-8") as fh:
            fh.write(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
