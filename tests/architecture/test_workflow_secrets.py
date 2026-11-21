# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G17a: GitHub workflow trust boundary, repo side (Q-012, Q-040; ADR-0099, ADR-0130 section 9).

``ci_environments.toml`` declares, per GitHub environment, the secrets it may hold and whether it is gated
(required reviewers plus a branch policy). The guard parses ``.github/workflows/*.yml`` and reports:

* ``secret-not-declared``: a job references a secret (other than ``GITHUB_TOKEN``) that its environment does not declare,
  or that is used in a job with no environment at all;
* ``ungated-environment``: a job uses secrets through an environment declared ``gated = false`` that is not declared
  ``prod_grade = false`` and has no ``main_only`` branch policy (ADR-0132: environments split by data sensitivity; only environments that hold no prod-read or
  prod-write material may stay ungated, and they declare so);
* ``prod-env-from-branch-trigger``: a gated (or undeclared ``prod*``) environment job in a workflow that a PR or non-main
  push can trigger, unless the job's whole ``if`` requires ``github.event_name != 'pull_request'`` (``&&`` only, never ``||``), every other
  trigger is dispatch/call/schedule/``push`` to main or tags, and the environment is gated or ``main_only``;
* ``environment-workflow-not-allowed``: an environment with ``only_workflows`` referenced from any other workflow file
  (``prod-restore-read`` is reachable only through ``terraform.yml``, called by ``restore-drill.yml`` alone);
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
# Result positions of an `a && 'x' || 'y'` expression; comparison operands (`== 'prod'`) are not environment names.
ENV_NAME = re.compile(r"(?:&&|\|\|)\s*'([a-z][a-z0-9-]*)'")
PLAIN_NAME = re.compile(r"^\$\{\{\s*'([a-z][a-z0-9-]*)'\s*\}\}$")
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
    if "${{" not in env:
        return [env]
    plain = PLAIN_NAME.match(env.strip())
    return [plain.group(1)] if plain else ENV_NAME.findall(env)


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


PR_SKIP = "github.event_name != 'pull_request'"
SAFE_NON_PR_TRIGGERS = {"workflow_dispatch", "workflow_call", "schedule"}


def _if_excludes_pull_requests(job: dict[str, Any]) -> bool:
    """True when the job's whole `if` requires `github.event_name != 'pull_request'` (an `&&` conjunct, never `||`)."""
    condition = " ".join(str(job.get("if", "")).split())
    if condition.startswith("${{") and condition.endswith("}}"):
        condition = condition[3:-2].strip()
    if "||" in condition:
        return False
    return PR_SKIP in [part.strip() for part in condition.split("&&")]


def _push_is_main_or_tags_only(push: Any) -> bool:
    if not isinstance(push, dict):
        return False
    branches: list[str] = push.get("branches") or []
    tags = push.get("tags")
    return (bool(branches) and set(branches) == {"main"}) or (not branches and bool(tags))


def _non_pr_triggers_are_safe(triggers: dict[str, Any]) -> bool:
    for name, value in triggers.items():
        if name == "pull_request" or name in SAFE_NON_PR_TRIGGERS:
            continue
        if name == "push" and _push_is_main_or_tags_only(value):
            continue
        return False
    return True


def _skips_pull_requests(
    job: dict[str, Any], triggers: dict[str, Any], spec: dict[str, Any]
) -> bool:
    """Exempt a PR-reachable workflow's job only when the PR path is skipped, no other branch trigger exists and the
    environment is gated or `main_only` (so the GitHub deployment-branch policy is the backstop)."""
    backstop = bool(spec.get("gated") or spec.get("main_only"))
    return backstop and _if_excludes_pull_requests(job) and _non_pr_triggers_are_safe(triggers)


def _is_gated_or_prod(env: str, declared: dict[str, Any]) -> bool:
    spec = declared.get(env)
    return bool(spec.get("gated") or spec.get("main_only")) if spec else env.startswith("prod")


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
            if (
                secrets
                and not spec.get("gated", False)
                and not spec.get("main_only", False)
                and spec.get("prod_grade", True)
            ):
                found.append(Violation(rel, 0, "ungated-environment", f"{name}: {env}"))
            if (
                _is_gated_or_prod(env, declared)
                and _branch_reachable(triggers)
                and not _skips_pull_requests(job, triggers, spec)
            ):
                found.append(Violation(rel, 0, "prod-env-from-branch-trigger", f"{name}: {env}"))
            only = spec.get("only_workflows")
            if only and Path(rel).name not in only:
                found.append(
                    Violation(rel, 0, "environment-workflow-not-allowed", f"{name}: {env}")
                )
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


def test_detects_gated_environment_in_pr_reachable_job_unless_skipped() -> None:
    declared = {"g": {"gated": True, "secrets": ["X"]}}
    body = "    environment: g\n    steps:\n      - run: ${{ secrets.X }}\n"
    reachable = f"on: pull_request\njobs:\n  a:\n{body}"
    skipped = f"on: pull_request\njobs:\n  a:\n    if: github.event_name != 'pull_request'\n{body}"
    assert [v.rule for v in scan_workflow("wf.yml", reachable, declared)] == [
        "prod-env-from-branch-trigger"
    ]
    assert not scan_workflow("wf.yml", skipped, declared)


def _pr_job(condition: str, extra_on: str = "") -> str:
    return (
        f"on:\n  pull_request:\n{extra_on}jobs:\n  a:\n    if: {condition}\n    environment: g\n"
        "    steps:\n      - run: ${{ secrets.X }}\n"
    )


_GATED = {"g": {"gated": True, "secrets": ["X"]}}
_SKIP = "github.event_name != 'pull_request'"


def test_pr_skip_exemption_accepts_exact_and_conjunction_only() -> None:
    assert not scan_workflow("wf.yml", _pr_job(_SKIP), _GATED)
    assert not scan_workflow("wf.yml", _pr_job("${{ " + _SKIP + " && inputs.x }}"), _GATED)


def test_pr_skip_exemption_rejects_or_conditions() -> None:
    for condition in (f"{_SKIP} || true", f"{_SKIP} || always()", f"(a || b) && {_SKIP}"):
        rules = [v.rule for v in scan_workflow("wf.yml", _pr_job(condition), _GATED)]
        assert rules == ["prod-env-from-branch-trigger"], condition


def test_pr_skip_exemption_rejects_branch_push_trigger() -> None:
    wide = "  push:\n    branches: ['**']\n"
    rules = [v.rule for v in scan_workflow("wf.yml", _pr_job(_SKIP, wide), _GATED)]
    assert rules == ["prod-env-from-branch-trigger"]
    main_push = "  push:\n    branches: [main]\n  workflow_dispatch:\n"
    assert not scan_workflow("wf.yml", _pr_job(_SKIP, main_push), _GATED)


def test_pr_skip_exemption_needs_gated_or_main_only_environment() -> None:
    undeclared = scan_workflow("wf.yml", _pr_job(_SKIP).replace("g\n", "prod-x\n"), {})
    assert "prod-env-from-branch-trigger" in [v.rule for v in undeclared]


def test_comparison_operands_are_not_environment_names() -> None:
    job = {"environment": "${{ matrix.env == 'prod' && 'prod-plan' || 'drill-plan' }}"}
    assert _environment_names(job) == ["prod-plan", "drill-plan"]
    assert _environment_names({"environment": "${{ 'drill' }}"}) == ["drill"]


def test_detects_environment_outside_allowed_workflows() -> None:
    declared = {"r": {"gated": True, "secrets": [], "only_workflows": ["terraform.yml"]}}
    workflow = "on: workflow_dispatch\njobs:\n  a:\n    environment: r\n    steps: []\n"
    assert [v.rule for v in scan_workflow("other.yml", workflow, declared)] == [
        "environment-workflow-not-allowed"
    ]
    assert not scan_workflow("terraform.yml", workflow, declared)


def test_ungated_environment_with_no_prod_material_is_allowed_when_declared() -> None:
    workflow = "on: workflow_dispatch\njobs:\n  a:\n    environment: d\n    steps:\n      - run: ${{ secrets.X }}\n"
    declared = {"d": {"gated": False, "prod_grade": False, "secrets": ["X"]}}
    assert not scan_workflow("wf.yml", workflow, declared)


def test_gated_environments_are_declared_gated_and_restricted() -> None:
    """ADR-0132: the prod-read environment is gated, main-only and used only through terraform.yml."""
    declared = declared_environments()
    spec = declared["prod-restore-read"]
    assert spec["gated"] is True
    assert spec["only_workflows"] == ["terraform.yml"]
    assert declared["prod"]["gated"] is True


def test_only_restore_drill_requests_the_prod_read_key() -> None:
    """H4-03: `restore_source: true` appears in restore-drill.yml only; explore drills never carry restore-source.env."""
    callers = {
        path.name
        for path in WORKFLOWS.glob("*.yml")
        if re.search(r"^\s+restore_source:\s*true\b", path.read_text(encoding="utf-8"), re.M)
    }
    assert callers == {"restore-drill.yml"}
