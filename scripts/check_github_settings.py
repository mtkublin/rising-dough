#!/usr/bin/env python3
"""Operator-run check of GitHub settings (ADR-0130 section 9, G17b, Q-012).

Read-only. Uses ``gh api`` with the operator's own authentication: no workflow,
no token, no writes. Prints a PASS/FAIL/SKIP table and exits 1 on any FAIL.

Expectations come from ADR-0099/0100/0121 and
``docs/plans/v3/runbooks/github-settings.md``:

- environment ``prod``: required reviewer, deployment branches ``main`` + tag ``v*``;
- ``prod-tailnet``: deployment branches ``main`` + tag ``v*``;
- ungated environments (``prod-plan``, ``drill-teardown``, ``drill-plan``): no reviewers;
- no ``prod-deploy`` environment (ADR-0111);
- no repo-level ``SCW_ACCESS_KEY`` / ``SCW_SECRET_KEY`` secrets;
- ``main`` is protected (ruleset or classic) with a pull request requirement, the
  required status checks, and no force pushes / deletions;
- the Actions permissions require SHA pinning when the API reports the setting;
- the live Tailscale ACL equals ``docs/plans/v3/runbooks/tailscale-acl.hujson``
  (T-Q238; needs ``TAILSCALE_API_TOKEN`` and ``TAILSCALE_OWNER_EMAIL`` in the
  environment, otherwise SKIP; the token is never printed).

Usage: ``uv run python scripts/check_github_settings.py [--repo OWNER/NAME]``
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from tailscale_acl_drift import OWNER_ENV, TOKEN_ENV, compare_live

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
REQUIRED_CHECKS = (
    "just ci (Python 3.12, ubuntu-latest)",
    "drill-gate",
    "tests/e2e (Chromium, Playwright container)",
)
GATED_ENVS = {"prod": True}
UNGATED_ENVS = ("prod-plan", "drill-teardown", "drill-plan")
RELEASE_REFS = {("branch", "main"), ("tag", "v*")}
FORBIDDEN_REPO_SECRETS = ("SCW_ACCESS_KEY", "SCW_SECRET_KEY")

Api = Callable[[str], Any]


@dataclass(frozen=True)
class Result:
    name: str
    status: str
    detail: str


def gh_api(path: str) -> Any:
    """GET ``path`` through the operator's ``gh`` auth. Raises on failure."""
    proc = subprocess.run(  # noqa: S603
        ["gh", "api", "-H", "Accept: application/vnd.github+json", path],  # noqa: S607
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"gh api {path} failed")
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def has_reviewers(env: Mapping[str, Any]) -> bool:
    return any(
        rule.get("type") == "required_reviewers" and bool(rule.get("reviewers"))
        for rule in env.get("protection_rules", [])
    )


def policies(api: Api, repo: str, env: str) -> set[tuple[str, str]]:
    data = api(f"repos/{repo}/environments/{env}/deployment-branch-policies")
    return {(p.get("type", "branch"), p["name"]) for p in data.get("branch_policies", [])}


def check_environments(api: Api, repo: str) -> list[Result]:
    envs = {e["name"]: e for e in api(f"repos/{repo}/environments").get("environments", [])}
    out: list[Result] = []
    for name in ("prod", "prod-tailnet"):
        if name not in envs:
            out.append(Result(f"env {name}", FAIL, "environment missing"))
            continue
        got = policies(api, repo, name)
        out.append(
            Result(
                f"env {name}: deploy refs main + tag v*",
                PASS if got == RELEASE_REFS else FAIL,
                f"found {sorted(got) or 'none (all branches allowed)'}",
            )
        )
    if "prod" in envs:
        out.append(
            Result(
                "env prod: required reviewer",
                PASS if has_reviewers(envs["prod"]) else FAIL,
                "reviewers configured" if has_reviewers(envs["prod"]) else "no required reviewer",
            )
        )
    for name in UNGATED_ENVS:
        if name not in envs:
            out.append(Result(f"env {name}", FAIL, "environment missing"))
        else:
            gated = has_reviewers(envs[name])
            out.append(
                Result(
                    f"env {name}: ungated",
                    FAIL if gated else PASS,
                    "has reviewers" if gated else "no reviewers",
                )
            )
    out.append(
        Result(
            "no env prod-deploy (ADR-0111)",
            FAIL if "prod-deploy" in envs else PASS,
            "exists, delete it" if "prod-deploy" in envs else "absent",
        )
    )
    return out


def check_repo_secrets(api: Api, repo: str) -> Result:
    names = {s["name"] for s in api(f"repos/{repo}/actions/secrets").get("secrets", [])}
    bad = sorted(names & set(FORBIDDEN_REPO_SECRETS))
    return Result(
        "no repo-level SCW secrets", FAIL if bad else PASS, f"found {bad}" if bad else "none"
    )


def _ruleset_rules(api: Api, repo: str) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = []
    for rs in api(f"repos/{repo}/rulesets"):
        detail = api(f"repos/{repo}/rulesets/{rs['id']}")
        if detail.get("enforcement") != "active":
            continue
        refs = detail.get("conditions", {}).get("ref_name", {}).get("include", [])
        if any(r in {"~DEFAULT_BRANCH", "refs/heads/main"} for r in refs):
            rules.extend(detail.get("rules", []))
    return rules


def check_main_protection(api: Api, repo: str) -> list[Result]:
    rules = _ruleset_rules(api, repo)
    types = {r["type"] for r in rules}
    contexts = {
        c["context"]
        for r in rules
        if r["type"] == "required_status_checks"
        for c in r.get("parameters", {}).get("required_status_checks", [])
    }
    classic: Mapping[str, Any] = {}
    if not rules:
        try:
            classic = api(f"repos/{repo}/branches/main/protection")
        except RuntimeError as exc:
            return [
                Result(
                    "main protection", FAIL, f"no active ruleset and no classic protection ({exc})"
                )
            ]
        contexts = set(classic.get("required_status_checks", {}).get("contexts", []))
    pr_required = "pull_request" in types or "required_pull_request_reviews" in classic
    no_force = ("non_fast_forward" in types and "deletion" in types) or (
        classic and not classic.get("allow_force_pushes", {}).get("enabled", True)
    )
    missing = [c for c in REQUIRED_CHECKS if c not in contexts]
    return [
        Result(
            "main: pull request required",
            PASS if pr_required else FAIL,
            "ok" if pr_required else "missing",
        ),
        Result(
            "main: required status checks",
            FAIL if missing else PASS,
            f"missing {missing}"
            if missing
            else f"{len(contexts)} checks incl. {', '.join(REQUIRED_CHECKS)}",
        ),
        Result(
            "main: no force push / deletion",
            PASS if no_force else FAIL,
            "ok" if no_force else "allowed",
        ),
    ]


def check_actions_pinning(api: Api, repo: str) -> Result:
    perms = api(f"repos/{repo}/actions/permissions")
    if "sha_pinning_required" not in perms:
        return Result("actions: SHA pinning required", SKIP, "setting not reported by the API")
    ok = bool(perms["sha_pinning_required"])
    return Result(
        "actions: SHA pinning required", PASS if ok else FAIL, "enforced" if ok else "not enforced"
    )


def check_allowed_actions(api: Api, repo: str) -> Result:
    """T-Q255 (Q-068): only selected actions may run (operator-set repo setting)."""
    perms = api(f"repos/{repo}/actions/permissions")
    allowed = perms.get("allowed_actions")
    if allowed is None:
        return Result("actions: allowed_actions selected", SKIP, "setting not reported by the API")
    ok = allowed == "selected"
    return Result(
        "actions: allowed_actions selected",
        PASS if ok else FAIL,
        "selected" if ok else str(allowed),
    )


def check_tailscale_acl(
    environ: Mapping[str, str] = os.environ, compare: Callable[[str, str], list[str]] = compare_live
) -> Result:
    """T-Q238 / OQ-24: live Tailscale ACL vs the runbook copy. SKIP without a token."""
    token, owner = environ.get(TOKEN_ENV, ""), environ.get(OWNER_ENV, "")
    name = "tailscale ACL matches runbook copy"
    if not token or not owner:
        return Result(name, SKIP, f"set {TOKEN_ENV} and {OWNER_ENV} to enable")
    try:
        drift = compare(token, owner)
    except (OSError, ValueError) as exc:
        return Result(name, FAIL, f"could not fetch ({type(exc).__name__})")
    return Result(name, FAIL if drift else PASS, "; ".join(drift) if drift else "identical")


def run_checks(api: Api, repo: str) -> list[Result]:
    sections: Sequence[Callable[[], list[Result]]] = (
        lambda: check_environments(api, repo),
        lambda: [check_repo_secrets(api, repo)],
        lambda: check_main_protection(api, repo),
        lambda: [check_actions_pinning(api, repo)],
        lambda: [check_allowed_actions(api, repo)],
        lambda: [check_tailscale_acl()],
    )
    results: list[Result] = []
    for section in sections:
        try:
            results.extend(section())
        except RuntimeError as exc:
            results.append(Result("api call", FAIL, str(exc)))
    return results


def render(results: Sequence[Result]) -> str:
    width = max(len(r.name) for r in results)
    return "\n".join(f"{r.status:5} {r.name:{width}}  {r.detail}" for r in results)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--repo", help="OWNER/NAME (default: the current repo via gh)")
    args = ap.parse_args(argv)
    repo = args.repo or gh_api("repos/{owner}/{repo}")["full_name"]
    results = run_checks(gh_api, repo)
    print(f"GitHub settings for {repo}\n{render(results)}")
    return 1 if any(r.status == FAIL for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
