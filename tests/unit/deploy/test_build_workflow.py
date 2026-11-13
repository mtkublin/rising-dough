"""Static assertions on the release pipeline workflows (ADR-0099, ADR-0037 §2). No network."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = ROOT / ".github" / "workflows"
MAIN_TAG_GATE = "type=raw,value=main,enable={{is_default_branch}}"


def _load(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((WORKFLOWS / name).read_text())
    return loaded


def _triggers(name: str) -> dict[str, Any]:
    wf: dict[Any, Any] = _load(name)
    # PyYAML parses the bare key `on` as boolean True.
    triggers: dict[str, Any] = wf[True] if True in wf else wf["on"]
    return triggers


def test_build_has_no_push_tag_or_release_trigger() -> None:
    triggers = _triggers("build.yml")

    assert set(triggers) == {"workflow_call", "workflow_dispatch"}
    assert {"image-tag", "image-digest"} <= set(triggers["workflow_call"]["outputs"])


def test_main_tag_stays_gated_by_default_branch() -> None:
    workflow = (WORKFLOWS / "build.yml").read_text()

    assert MAIN_TAG_GATE in workflow
    assert workflow.count("value=main") == 1


def test_release_chain_is_ci_build_tf_apply_deploy() -> None:
    jobs = _load("release.yml")["jobs"]

    assert jobs["ci"].get("needs") is None
    assert jobs["build"]["needs"] == "ci"
    assert jobs["tf-apply-prod"]["needs"] == "build"
    assert set(jobs["deploy-prod"]["needs"]) == {"build", "tf-apply-prod"}
    assert _triggers("release.yml")["push"]["branches"] == ["main"]


def test_release_serialises_prod_releases() -> None:
    concurrency = _load("release.yml")["concurrency"]

    assert concurrency == {"group": "release-prod", "cancel-in-progress": False}


def test_apply_and_deploy_have_no_independent_triggers() -> None:
    for name in ("terraform.yml", "deploy.yml"):
        triggers = _triggers(name)
        assert "push" not in triggers, name
        assert "workflow_run" not in triggers, name
        assert "workflow_call" in triggers, name


def test_release_is_the_only_prod_caller() -> None:
    callers = [
        p.name
        for p in WORKFLOWS.glob("*.yml")
        if "uses: ./.github/workflows/terraform.yml" in p.read_text()
        and "env: prod" in p.read_text()
    ]

    assert callers == ["release.yml"]
