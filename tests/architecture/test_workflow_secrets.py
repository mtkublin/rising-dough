# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G17a: GitHub workflow trust boundary, repo side (Q-012, Q-040; ADR-0099, ADR-0130 section 9).

``ci_environments.toml`` declares, per GitHub environment, the secrets it may hold and whether it is gated
(required reviewers plus a branch policy). The guard parses ``.github/workflows/*.yml`` and reports:

* ``secret-not-declared``: a job references a secret (other than ``GITHUB_TOKEN``) that its environment does not declare,
  or that is used in a job with no environment at all;
* ``ungated-environment``: a job uses secrets through an environment declared ``gated = false`` (Q-012 debt);
* ``prod-env-from-branch-trigger``: a ``prod*`` environment job in a workflow that a PR or non-main push can trigger;
* ``cosign-identity-unpinned``: the image-signature identity regexp accepts any ref (Q-040).

A new environment or secret needs an entry in ``ci_environments.toml`` and an operator go (CLAUDE.md Releases &
environments). The live settings check (G17b) is the operator-run ``scripts/ci/check_github_settings.py``.
Allowlist: ``allowlists/workflow_trust.toml``.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

from tests.architecture._ratchet import REPO_ROOT, Violation, assert_ratchet

GUARD = "workflow_trust"
HEADER = "G17a workflow_trust: workflow trust-boundary debt (Q-012, Q-040; declared in ci_environments.toml)."
DECLARED = Path(__file__).resolve().parent / "ci_environments.toml"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
USER_DATA = REPO_ROOT / "terraform" / "modules" / "compute" / "user_data.tf"
SECRET = re.compile(r"secrets\.([A-Za-z0-9_]+)")
ENV_NAME = re.compile(r"'([a-z][a-z0-9-]*)'")
PINNED = re.compile(r"refs/heads/main")
TEACH = (
    "G17 workflow trust boundary: a job may use only the secrets its environment declares in "
    "tests/architecture/ci_environments.toml, prod environments are reachable only from main, and the cosign identity "
    "must be pinned to refs/heads/main or version tags. A new environment or secret needs a toml entry and an "
    "operator go (CLAUDE.md Releases & environments; Q-012, Q-040)."
)


def _environment_names(job: dict[str, Any]) -> list[str]:
    env = job.get("environment")
    if isinstance(env, dict):
        env = env.get("name")
    if not isinstance(env, str):
        return []
    return ENV_NAME.findall(env) if "${{" in env else [env]


def _triggers(workflow: dict[Any, Any]) -> dict[str, Any]:
    triggers = workflow.get(
        True, workflow.get("on", {})
    )  # PyYAML parses a bare `on:` key as boolean True
    if isinstance(triggers, str):
        return {triggers: None}
    if isinstance(triggers, list):
        return dict.fromkeys(triggers)
    return triggers or {}


def _branch_reachable(triggers: dict[str, Any]) -> bool:
    if "pull_request" in triggers or "pull_request_target" in triggers:
        return True
    push = triggers.get("push")
    if isinstance(push, dict):
        branches: list[str] = push.get("branches") or []
        return bool(branches) and set(branches) != {"main"}
    return "push" in triggers


def scan_workflow(rel: str, text: str, declared: dict[str, Any]) -> list[Violation]:
    workflow = yaml.safe_load(text) or {}
    triggers = _triggers(workflow)
    found: list[Violation] = []
    for name, job in (workflow.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        secrets = sorted(set(SECRET.findall(yaml.safe_dump(job))) - {"GITHUB_TOKEN"})
        envs = _environment_names(job)
        for env in envs:
            spec = declared.get(env, {})
            if secrets and not spec.get("gated", False):
                found.append(Violation(rel, 0, "ungated-environment", f"{name}: {env}"))
            if env.startswith("prod") and _branch_reachable(triggers):
                found.append(Violation(rel, 0, "prod-env-from-branch-trigger", f"{name}: {env}"))
        for secret in secrets:
            allowed: set[str] = set()
            for e in envs:
                allowed |= set(declared.get(e, {}).get("secrets", []))
            if secret not in allowed:
                found.append(Violation(rel, 0, "secret-not-declared", f"{name}: {secret}"))
    return found


def cosign_violations(rel: str, text: str) -> list[Violation]:
    match = re.search(r'identity_regexp\s*=\s*"([^"]*)"', text)
    if match and not PINNED.search(match.group(1)):
        return [Violation(rel, 0, "cosign-identity-unpinned", match.group(1))]
    return []


def declared_environments() -> dict[str, Any]:
    environments: dict[str, Any] = tomllib.loads(DECLARED.read_text(encoding="utf-8")).get(
        "environment", {}
    )
    return environments


def collect() -> list[Violation]:
    declared = declared_environments()
    found: list[Violation] = []
    for path in sorted(WORKFLOWS.glob("*.yml")):
        found += scan_workflow(
            path.relative_to(REPO_ROOT).as_posix(), path.read_text(encoding="utf-8"), declared
        )
    if USER_DATA.is_file():
        found += cosign_violations(
            USER_DATA.relative_to(REPO_ROOT).as_posix(), USER_DATA.read_text(encoding="utf-8")
        )
    return found


def meta(v: Violation) -> tuple[str, str, str, str]:
    finding = "Q-040" if v.rule == "cosign-identity-unpinned" else "Q-012"
    return "entry", finding, "", ""


def test_workflow_secrets_match_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_detects_prod_secret_in_branch_triggered_job() -> None:
    workflow = (
        "on:\n  pull_request:\njobs:\n  apply:\n    environment: prod\n    steps:\n"
        "      - run: echo ${{ secrets.AGE_KEY }}\n"
    )
    declared = {"prod": {"gated": True, "secrets": []}}
    rules = {v.rule for v in scan_workflow("wf.yml", workflow, declared)}
    assert {"prod-env-from-branch-trigger", "secret-not-declared"} <= rules


def test_detects_secret_without_environment_and_ungated_environment() -> None:
    workflow = "on: workflow_dispatch\njobs:\n  a:\n    steps:\n      - run: ${{ secrets.X }}\n"
    assert [v.rule for v in scan_workflow("wf.yml", workflow, {})] == ["secret-not-declared"]
    gated = "on: workflow_dispatch\njobs:\n  a:\n    environment: e\n    steps:\n      - run: ${{ secrets.X }}\n"
    rules = {
        v.rule for v in scan_workflow("wf.yml", gated, {"e": {"secrets": ["X"], "gated": False}})
    }
    assert rules == {"ungated-environment"}


def test_detects_unpinned_cosign_identity() -> None:
    assert cosign_violations(
        "u.tf",
        'identity_regexp = "^https://github\\\\.com/o/r/\\\\.github/workflows/build\\\\.yml@"',
    )
    assert not cosign_violations("u.tf", 'identity_regexp = "^x/build\\\\.yml@refs/heads/main$"')
