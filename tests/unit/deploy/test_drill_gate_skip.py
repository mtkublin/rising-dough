"""T-D147 / ADR-0121: drill-gate skip classifier and workflow shape. No network."""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ci" / "drill_gate_skip.py"
WORKFLOWS = ROOT / ".github" / "workflows"
SKIP_WORKFLOW = "drill-gate-skip.yml"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("drill_gate_skip", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


skip = _load()


@pytest.mark.parametrize(
    "paths",
    [
        ["docs/adr/0121-x.md"],
        ["docs/plans/v3/tasks.md", "docs/CHANGELOG.md"],
        ["docs/diagram.png"],
        ["docs/requirements.md", "docs/plans/v3/runbooks/drill.md"],
    ],
)
def test_non_deploy_changes_skip(paths: list[str]) -> None:
    verdict, offenders = skip.classify(paths)
    assert verdict == "skip"
    assert offenders == []


@pytest.mark.parametrize(
    "path",
    [
        "src/budget_planner/README.md",
        "src/budget_planner/main.py",
        "migrations/0001_init.sql",
        "migrations/notes.md",
        "terraform/README.md",
        "terraform/main.tf",
        "deploy/docker-entrypoint.sh",
        "deploy/README.md",
        "scripts/ci/ref_guard.py",
        "scripts/README.md",
        ".github/workflows/ci.yml",
        ".github/workflows/drill-gate-skip.yml",
        ".github/PULL_REQUEST_TEMPLATE.md",
        "Dockerfile",
        ".dockerignore",
        "pyproject.toml",
        "uv.lock",
        "justfile",
        ".pre-commit-config.yaml",
        "unknown.bin",
        "Docs/readme.txt",
        "docs/../src/x.py",
        "/etc/passwd",
        "licensefile",
        # T-Q238 (Q-042): previously treated as inert, each changes pipeline or agent behaviour.
        ".claude/settings.json",
        ".claude/skills/orchestrator-mode/SKILL.md",
        "tests/render/render_check.py",
        "tests/conftest.py",
        "tests/unit/deploy/test_x.py",
        "CLAUDE.md",
        "README.md",
        "LICENSE",
        "LICENSE_run.sh",
        "notes/idea.md",
        "./docs/x.md",
        "SRC/x.md",
        "docs/plans/v3/runbooks/restore-log.md",
    ],
)
def test_deploy_relevant_paths_gate(path: str) -> None:
    verdict, offenders = skip.classify([path])
    assert verdict == "gate"
    assert offenders == [path]


def test_mixed_docs_and_src_gates_and_lists_only_offenders() -> None:
    verdict, offenders = skip.classify(["docs/a.md", "src/x.py", "docs/b.md"])
    assert verdict == "gate"
    assert offenders == ["src/x.py"]


def test_empty_diff_fails_closed() -> None:
    assert skip.classify([]) == ("gate", [])
    assert skip.classify(["", "  "]) == ("gate", [])


def test_rename_from_docs_to_src_gates() -> None:
    verdict, offenders = skip.classify(["docs/old.md", "src/new.md"])
    assert verdict == "gate"
    assert offenders == ["src/new.md"]


def test_rename_from_src_to_docs_gates() -> None:
    verdict, offenders = skip.classify(["src/old.py", "docs/new.md"])
    assert verdict == "gate"
    assert offenders == ["src/old.py"]


def test_cli_prints_verdict_then_offenders() -> None:
    def run(stdin: str) -> list[str]:
        out = subprocess.run(  # noqa: S603
            [sys.executable, str(SCRIPT)], input=stdin, capture_output=True, text=True, check=True
        )
        return out.stdout.splitlines()

    assert run("docs/a.md\n") == ["skip"]
    assert run("docs/a.md\nsrc/x.py\n") == ["gate", "src/x.py"]
    assert run("") == ["gate"]


# --- workflow shape ---------------------------------------------------------


def _wf() -> dict[Any, Any]:
    loaded: dict[Any, Any] = yaml.safe_load((WORKFLOWS / SKIP_WORKFLOW).read_text())
    return loaded


def test_workflow_triggers_on_pull_request_to_main_only() -> None:
    wf = _wf()
    triggers = wf[True] if True in wf else wf["on"]
    assert set(triggers) == {"pull_request_target"}
    assert triggers["pull_request_target"]["branches"] == ["main"]
    assert set(triggers["pull_request_target"]["types"]) == {
        "opened",
        "synchronize",
        "reopened",
        "ready_for_review",
    }


def test_workflow_permissions_are_minimal() -> None:
    wf = _wf()
    assert wf["permissions"] == {
        "statuses": "write",
        "contents": "read",
        "pull-requests": "read",
    }
    for job in wf["jobs"].values():
        assert "permissions" not in job or set(job["permissions"]) <= {
            "statuses",
            "contents",
            "pull-requests",
        }


def test_workflow_uses_exact_drill_gate_context() -> None:
    drill = (WORKFLOWS / "drill.yml").read_text()
    contexts = set(re.findall(r"context=(\S+)", drill))
    assert contexts == {"drill-gate"}
    text = (WORKFLOWS / SKIP_WORKFLOW).read_text()
    assert set(re.findall(r"context=(\S+)", text)) == contexts
    assert "state=success" in text
    assert "skipped: no deploy-relevant changes (ADR-0121)" in text


def test_workflow_never_posts_failure_or_pending() -> None:
    text = (WORKFLOWS / SKIP_WORKFLOW).read_text()
    states = set(re.findall(r"state=(\S+)", text))
    assert states == {"success"}


def test_workflow_actions_are_sha_pinned() -> None:
    text = (WORKFLOWS / SKIP_WORKFLOW).read_text()
    refs = re.findall(r"^\s*-?\s*uses:\s*(\S+)", text, flags=re.M)
    assert refs
    for ref in refs:
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref), ref


def test_workflow_runs_classifier_from_base_not_pr_head() -> None:
    text = (WORKFLOWS / SKIP_WORKFLOW).read_text()
    assert "scripts/ci/drill_gate_skip.py" in text
    assert "pull_request.base.ref" in text
    assert "pull_request.base.sha" not in text


def test_workflow_never_checks_out_pr_code() -> None:
    steps = [s for job in _wf()["jobs"].values() for s in job["steps"]]
    checkouts = [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@")]
    assert checkouts
    for step in checkouts:
        assert step["with"]["ref"] == "${{ github.event.pull_request.base.ref }}"
        assert step["with"]["persist-credentials"] is False
    text = (WORKFLOWS / SKIP_WORKFLOW).read_text()
    assert "head.ref" not in text
    assert "refs/pull" not in text
    assert "merge" not in text.replace("merge ref", "")


def test_run_blocks_do_not_interpolate_pr_context() -> None:
    steps = [s for job in _wf()["jobs"].values() for s in job["steps"]]
    for step in steps:
        run = step.get("run", "")
        assert "${{" not in run, run
        for value in step.get("env", {}).values():
            for expr in re.findall(r"\$\{\{\s*([^}]*?)\s*\}\}", str(value)):
                if expr.startswith("github.event.pull_request."):
                    assert expr in {
                        "github.event.pull_request.number",
                        "github.event.pull_request.head.sha",
                    }, expr


def test_missing_classifier_yields_gate_and_exits_zero(tmp_path: Path) -> None:
    steps = [s for job in _wf()["jobs"].values() for s in job["steps"]]
    classify = next(s for s in steps if s.get("id") == "classify")
    out = tmp_path / "out.txt"
    summary = tmp_path / "summary.md"
    env = {
        "PATH": "/usr/bin:/bin",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_OUTPUT": str(out),
        "GITHUB_STEP_SUMMARY": str(summary),
        "GH_TOKEN": "x",
        "REPO": "o/r",
        "PR": "1",
    }
    proc = subprocess.run(  # noqa: S603
        ["/bin/bash", "-c", classify["run"]],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "verdict=gate" in out.read_text()
    assert "classifier not on base; real gate required" in summary.read_text()


# --- T-Q238: allowlist is docs only; verdict bound to the head SHA ----------

# docs/ paths that appear only in comments or messages of .github/ and scripts/ci/.
REFERENCE_ONLY_DOCS = {
    "docs/plans/v3/runbooks/disaster-recovery.md",
    "docs/plans/v3/runbooks/drill.md",
    "docs/plans/v3/runbooks/key-rotation.md",
    # scripts/ci/check_item.py (T-Q326): orchestrator DoD hotspot names, never read by a pipeline.
    "docs/CHANGELOG.md",
    "docs/adr/README.md",
}


def test_allowlist_is_docs_only() -> None:
    assert skip.SAFE_DIR == "docs"
    assert not hasattr(skip, "SAFE_DIRS")


def test_no_pipeline_file_reads_a_skippable_docs_path() -> None:
    referenced: set[str] = set()
    for root in (ROOT / ".github", ROOT / "scripts" / "ci"):
        for f in root.rglob("*"):
            if f.is_file() and f != SCRIPT and f.suffix in {".yml", ".yaml", ".py", ".sh", ""}:
                referenced |= set(re.findall(r"docs/[A-Za-z0-9_./-]*[A-Za-z0-9_]", f.read_text()))
    referenced = {r for r in referenced if r.endswith((".md", ".toml", ".json", ".txt", ".yml"))}
    unclassified = referenced - set(skip.DOCS_CONSUMED_BY_PIPELINE) - REFERENCE_ONLY_DOCS
    assert not unclassified, f"classify these as consumed (gate) or reference-only: {unclassified}"
    for path in skip.DOCS_CONSUMED_BY_PIPELINE:
        assert skip.classify([path])[0] == "gate"


def test_workflow_binds_verdict_to_live_head_sha() -> None:
    text = (WORKFLOWS / SKIP_WORKFLOW).read_text()
    assert re.search(r"pulls/\$\{PR\}\"? *--jq '?\.head\.sha", text)
    post = text.split("Post drill-gate success")[1]
    assert "live" in post
    assert post.index("head.sha") < post.index("state=success")
    assert "exit 0" in post.split("state=success")[0]
