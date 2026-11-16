"""Shared ref and tag guards for the release workflows (ADR-0099, ADR-0109).

Prod runs only from `main`, or from a SemVer `v*` tag whose commit is an
ancestor of `origin/main`. One script serves release.yml, build.yml,
terraform.yml, deploy.yml and rollback.yml so the rule lives in one place.

Subcommands (exit 0 = ok, 1 = refused, message on stderr):
  ref --ref REF [--sha SHA]    REF is refs/heads/main, or refs/tags/vX.Y.Z on main.
  deploy-tag TAG               TAG is sha-<7..40 hex> or vX.Y.Z.
  rollback-target VALUE        VALUE is vX.Y.Z, sha-<hex> or bare hex; prints the tag.
"""

# ruff: noqa: S603, S607  # fixed git argv, no shell
from __future__ import annotations

import argparse
import re
import subprocess  # nosec B404
import sys
from collections.abc import Callable, Sequence

MAIN_REF = "refs/heads/main"
TAG_PREFIX = "refs/tags/"
SEMVER_TAG = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
SHA_TAG = re.compile(r"^sha-[0-9a-f]{7,40}$")
BARE_SHA = re.compile(r"^[0-9a-f]{7,40}$")

IsAncestor = Callable[[str], bool]


class GuardError(ValueError):
    """Raised when a ref or tag is not allowed to reach prod."""


def is_semver_tag(tag: str) -> bool:
    return SEMVER_TAG.fullmatch(tag) is not None


def validate_deploy_tag(tag: str) -> str:
    if SHA_TAG.fullmatch(tag) or is_semver_tag(tag):
        return tag
    raise GuardError(f"image tag must be sha-<hex> or vMAJOR.MINOR.PATCH; got '{tag}'")


def resolve_rollback_target(value: str) -> str:
    """Normalise a rollback input to an image tag (bare hex -> sha-<first 7>)."""
    if is_semver_tag(value):
        return value
    if SHA_TAG.fullmatch(value):
        return value
    if BARE_SHA.fullmatch(value):
        return f"sha-{value[:7]}"
    raise GuardError(f"target must be vMAJOR.MINOR.PATCH, sha-<hex> or a git SHA; got '{value}'")


def check_ref(ref: str, tag_commit_on_main: IsAncestor, sha: str = "HEAD") -> str:
    """Return a description of why `ref` is allowed, or raise GuardError."""
    if ref == MAIN_REF:
        return "main"
    if ref.startswith(TAG_PREFIX):
        tag = ref.removeprefix(TAG_PREFIX)
        if not is_semver_tag(tag):
            raise GuardError(f"tag '{tag}' is not SemVer vMAJOR.MINOR.PATCH")
        if not tag_commit_on_main(sha):
            raise GuardError(f"tag {tag} ({sha[:12]}) is not an ancestor of origin/main")
        return f"tag {tag} on main"
    raise GuardError(f"prod runs only from main or a v* tag on main (got {ref})")


def git_is_ancestor_of_main(sha: str) -> bool:
    """Fetch origin/main and test ancestry; fetch failure is a refusal, not a pass."""
    fetch = subprocess.run(  # nosec B603 B607
        ["git", "fetch", "--quiet", "--no-tags", "origin", "main:refs/remotes/origin/main"],
        check=False,
        capture_output=True,
        text=True,
    )
    if fetch.returncode != 0:
        raise GuardError(f"cannot fetch origin/main: {fetch.stderr.strip()}")
    probe = subprocess.run(  # nosec B603 B607
        ["git", "merge-base", "--is-ancestor", sha, "origin/main"],
        check=False,
        capture_output=True,
    )
    return probe.returncode == 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    ref = sub.add_parser("ref")
    ref.add_argument("--ref", required=True)
    ref.add_argument("--sha", default="HEAD")
    sub.add_parser("deploy-tag").add_argument("tag")
    sub.add_parser("rollback-target").add_argument("value")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "ref":
            print(check_ref(args.ref, git_is_ancestor_of_main, args.sha))
        elif args.command == "deploy-tag":
            print(validate_deploy_tag(args.tag))
        else:
            print(resolve_rollback_target(args.value))
    except GuardError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
