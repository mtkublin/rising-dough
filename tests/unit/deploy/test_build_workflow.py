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


def test_release_chain_is_guard_ci_build_tf_apply() -> None:
    jobs = _load("release.yml")["jobs"]

    assert jobs["guard"].get("needs") is None
    assert jobs["ci"]["needs"] == "guard"
    assert set(jobs["build"]["needs"]) == {"guard", "ci"}
    assert set(jobs["tf-apply-prod"]["needs"]) == {"guard", "build"}
    # ADR-0111: the apply is the release; no SSH deploy job. T-D155: the tailnet
    # cleanup after a VM replacement is not a deploy step.
    assert set(jobs) == {"guard", "ci", "build", "tf-apply-prod", "tailnet-cleanup-prod"}


def test_release_triggers_on_published_release_not_push() -> None:
    """ADR-0109: merging to main builds nothing for prod."""
    triggers = _triggers("release.yml")

    assert set(triggers) == {"release", "workflow_dispatch"}
    assert triggers["release"] == {"types": ["published"]}
    tag_input = triggers["workflow_dispatch"]["inputs"]["tag"]
    assert tag_input["required"] is True
    assert tag_input["type"] == "string"


def test_release_guard_runs_the_shared_script_with_full_history() -> None:
    steps = _load("release.yml")["jobs"]["guard"]["steps"]
    checkout = next(s for s in steps if "actions/checkout" in s.get("uses", ""))
    runs = " ".join(s.get("run", "") for s in steps)

    assert checkout["with"]["fetch-depth"] == 0
    assert 'scripts/ci/ref_guard.py ref --ref "${GITHUB_REF}"' in runs


def test_prod_gets_the_digest_pinned_version_through_inputs_only() -> None:
    jobs = _load("release.yml")["jobs"]
    ref = "${{ needs.guard.outputs.tag }}@${{ needs.build.outputs.image-digest }}"

    assert jobs["tf-apply-prod"]["with"]["image_ref"] == ref


def test_build_also_tags_the_version_on_release_refs() -> None:
    workflow = (WORKFLOWS / "build.yml").read_text()

    assert (
        "type=raw,value=${{ github.ref_name }},enable=${{ startsWith(github.ref, 'refs/tags/v') }}"
        in workflow
    )
    assert "type=raw,value=sha-${{ steps.sha.outputs.short }}" in workflow


def test_no_workflow_hardcodes_a_main_only_ref_check_for_prod() -> None:
    for name in ("terraform.yml", "rollback.yml"):
        text = (WORKFLOWS / name).read_text()
        assert '!= "refs/heads/main"' not in text, name
        assert "scripts/ci/ref_guard.py ref" in text, name


def test_ssh_deploy_workflow_is_gone() -> None:
    # ADR-0111: Terraform declares the host state; no workflow pushes into the host.
    assert not (WORKFLOWS / "deploy.yml").exists()
    assert not any("deploy.yml" in p.read_text() for p in WORKFLOWS.glob("*.yml"))


def test_rollback_validates_target_through_the_script() -> None:
    wf = _load("rollback.yml")
    inputs = _triggers("rollback.yml")["workflow_dispatch"]["inputs"]
    text = (WORKFLOWS / "rollback.yml").read_text()

    assert "image_sha" not in inputs
    assert inputs["target"]["required"] is False
    assert 'ref_guard.py rollback-target "${RAW_TARGET}"' in text
    assert wf["permissions"]["contents"] == "read"
    # ADR-0111: a rollback is an approved apply through terraform.yml.
    apply = wf["jobs"]["apply"]
    assert apply["uses"] == "./.github/workflows/terraform.yml"
    assert apply["with"]["rollback"] is True
    assert apply["with"]["image_ref"] == "${{ needs.target.outputs.ref }}"


def test_release_serialises_prod_releases() -> None:
    concurrency = _load("release.yml")["concurrency"]

    assert concurrency == {"group": "release-prod", "cancel-in-progress": False}


def test_apply_has_no_independent_triggers() -> None:
    for name in ("terraform.yml",):
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


def test_build_guard_lets_reusable_calls_through() -> None:
    """T-D122: in a called workflow github.event_name/ref are the caller's, so a drill
    gate dispatched on a branch must not be skipped. Direct dispatch stays main-only."""
    triggers = _triggers("build.yml")
    called = triggers["workflow_call"]["inputs"]["called"]
    guard = _load("build.yml")["jobs"]["build-and-push"]["if"]

    assert called == {"type": "boolean", "default": True, "description": called["description"]}
    assert "called" not in (triggers["workflow_dispatch"] or {}).get("inputs", {})
    assert guard == (
        "inputs.called || github.ref == 'refs/heads/main' || startsWith(github.ref, 'refs/tags/v')"
    )
