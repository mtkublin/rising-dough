"""T-Q306(d)(e) / ADR-0149: drill.yml mode=gate is the upgrade drill (workflow wiring)."""

from __future__ import annotations

import itertools
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
DRILL = ROOT / ".github" / "workflows" / "drill.yml"
MARKER = ROOT / "scripts" / "ci" / "rehearsal_marker.sh"
TERRAFORM = "./.github/workflows/terraform.yml"
GATE_MIN_TTL = 240


def _jobs() -> dict[str, Any]:
    loaded: dict[Any, Any] = yaml.safe_load(DRILL.read_text())
    jobs: dict[str, Any] = loaded["jobs"]
    return jobs


def _needs(job: dict[str, Any]) -> set[str]:
    needs = job.get("needs") or []
    return {needs} if isinstance(needs, str) else set(needs)


def _ancestors(jobs: dict[str, Any], name: str) -> set[str]:
    seen: set[str] = set()
    todo = list(_needs(jobs[name]))
    while todo:
        job = todo.pop()
        if job not in seen:
            seen.add(job)
            todo.extend(_needs(jobs[job]))
    return seen


def _runs(job: dict[str, Any]) -> str:
    return "\n".join(str(s.get("run", "")) for s in job.get("steps", []))


def _code() -> str:
    return "\n".join(ln for ln in DRILL.read_text().splitlines() if not ln.lstrip().startswith("#"))


def test_phase_order_follows_needs() -> None:
    jobs = _jobs()
    chain = [
        "baseline",
        "apply-baseline",
        "smoke-baseline",
        "seed",
        "detect",
        "apply-upgrade",
        "converge",
        "verify",
        "apply-rollback",
        "verify-rollback",
        "teardown",
    ]
    for earlier, later in itertools.pairwise(chain):
        assert earlier in _ancestors(jobs, later), f"{later} must come after {earlier}"
    assert {"writer-started", "detect"} <= _needs(jobs["apply-upgrade"])
    assert {"writer", "converge"} <= _needs(jobs["verify"])
    assert "writer" not in _needs(jobs["teardown"])  # ends only when the host is destroyed


def test_baseline_apply_passes_terraform_ref_and_the_others_do_not() -> None:
    jobs = _jobs()
    base = jobs["apply-baseline"]
    assert base["uses"] == TERRAFORM
    assert base["with"]["terraform_ref"] == "${{ needs.baseline.outputs.tag }}"
    assert base["with"]["image_ref"] == "${{ needs.baseline.outputs.ref }}"
    assert base["with"]["drill_allow_empty_db"] == "true"
    for name in ("apply-upgrade", "apply-rollback", "teardown", "apply"):
        assert jobs[name]["uses"] == TERRAFORM
        assert "terraform_ref" not in jobs[name]["with"], name
    for name in ("apply-baseline", "apply-upgrade", "apply-rollback"):
        assert jobs[name]["with"]["env"] == "drill"
        assert jobs[name]["with"]["drill_expires_at"] == "${{ needs.ttl.outputs.expires-at }}"


def test_upgrade_apply_runs_the_pr_image_and_rollback_returns_the_baseline() -> None:
    jobs = _jobs()
    upgrade = jobs["apply-upgrade"]["with"]
    assert upgrade["image_ref"] == (
        "${{ needs.build.outputs.image-tag }}@${{ needs.build.outputs.image-digest }}"
    )
    assert "rollback" not in upgrade
    rollback = jobs["apply-rollback"]["with"]
    assert rollback["rollback"] is True
    assert rollback["image_ref"] == "${{ needs.baseline.outputs.ref }}"
    # Same run id as the baseline: this is the creating run (test_drill_run_id.py).
    assert "reuse_drill_run_id" not in upgrade and "reuse_drill_run_id" not in rollback


def test_rollback_runs_only_on_the_in_place_path() -> None:
    rollback = _jobs()["apply-rollback"]
    condition = str(rollback["if"])
    assert "needs.detect.outputs.replaced == 'false'" in condition
    assert "needs.apply-upgrade.outputs.server_replaced == 'false'" in condition
    assert "verify" in _needs(rollback)


def test_detection_is_a_plan_checked_against_the_apply() -> None:
    jobs = _jobs()
    detect = _runs(jobs["detect"])
    assert "terraform plan" in detect and "-lock=false" in detect
    assert "host_release.py replaced" in detect
    assert "terraform apply" not in detect
    assert jobs["detect"]["environment"] == "drill-plan"
    converge = _runs(jobs["converge"])
    assert 'test "${EXPECTED}" = "${OBSERVED}"' in converge
    assert jobs["converge"]["env"]["EXPECTED"] == "${{ needs.detect.outputs.replaced }}"
    assert (
        jobs["converge"]["env"]["OBSERVED"] == "${{ needs.apply-upgrade.outputs.server_replaced }}"
    )


def test_replacement_path_waits_for_restore_and_cleans_the_tailnet() -> None:
    converge = _jobs()["converge"]
    steps = {str(s.get("name", "")): s for s in converge["steps"]}
    cleanup = next(s for n, s in steps.items() if n.startswith("Remove the old node"))
    assert "server_replaced == 'true'" in cleanup["if"]
    assert "--replaced-name" in cleanup["run"] and "--created-after" in cleanup["run"]
    ready = next(s for n, s in steps.items() if n.startswith("Wait for /ready"))
    assert "server_replaced == 'true'" in ready["with"]["require-restore"]
    verify = _runs(_jobs()["verify"])
    assert '.result == "restored" and .generation == $gen' in verify
    assert "PRAGMA integrity_check" in verify
    assert 'if [ "${max}" -lt "${WRITER_LAST}" ]' in verify


def test_in_place_verify_checks_generation_and_stops_the_writer() -> None:
    jobs = _jobs()
    assert 'test "${gen}" = "${SEED_GENERATION}"' in _runs(jobs["verify"])
    stop = next(s for s in jobs["converge"]["steps"] if s["name"].startswith("Stop the writer"))
    assert "server_replaced == 'false'" in stop["if"]
    assert "-- stop" in stop["run"]


def test_seed_copies_the_demo_db_from_the_tag_and_renders_the_pr_helper() -> None:
    seed = _runs(_jobs()["seed"])
    assert 'git show "refs/tags/${TAG}:data/demo.sqlite" > demo.sqlite' in seed
    assert "render_seed_demo.py" in seed
    assert "'cat > /tmp/seed-demo.sqlite' < demo.sqlite" in seed
    assert "sudo bash /tmp/seed-demo.sh /tmp/seed-demo.sqlite" in seed
    assert "scp" not in seed
    # T-Q302: the seeded tables must be non-empty.
    for table in ("accounts", "transactions", "categories"):
        assert table in seed
    assert "rehearsal_marker.sh" in seed and "generation" in seed


def test_writer_steps_do_not_inherit_errexit() -> None:
    step = next(s for s in _jobs()["writer"]["steps"] if s.get("id") == "write")
    assert step["run"].lstrip().splitlines()[0].startswith("set +e")
    assert 'rc="${PIPESTATUS[0]}"' in step["run"]
    assert "writer-until" in step["run"]


def test_drill_gate_is_posted_only_from_gate_start_and_gate_result() -> None:
    jobs = _jobs()
    posting = {
        name
        for name, job in jobs.items()
        if "context=drill-gate" in _runs(job) or "statuses" in (job.get("permissions") or {})
    }
    assert posting == {"gate-start", "gate-result"}
    start = _runs(jobs["gate-start"])
    assert "state=pending" in start and "state=success" not in start
    result = jobs["gate-result"]
    assert "teardown" not in _needs(result)
    run = _runs(result)
    assert 'desc="${desc:0:140}"' in run
    for phase in ("baseline", "seed", "upgrade", "rollback"):
        assert f'phase="{phase}"' in run


def test_verdict_names_the_failing_phase_and_stays_within_the_status_limit() -> None:
    run = _runs(_jobs()["gate-result"])
    assert 'desc="drill gate failed in phase: ${phase}"' in run
    # A rollback phase is required on the in-place path and skipped by design otherwise.
    assert '[ "${REPLACED}" = "false" ]' in run and '[ "${REPLACED}" = "true" ]' in run
    assert len("drill gate failed in phase: ci/build") <= 140


def test_teardown_always_runs_once_an_apply_was_attempted() -> None:
    teardown = _jobs()["teardown"]
    condition = " ".join(str(teardown["if"]).split())
    assert "always()" in condition
    assert "needs.apply-baseline.result != 'skipped'" in condition
    assert teardown["with"] == {"env": "drill", "destroy": True}


def test_gate_ttl_covers_the_longer_run() -> None:
    script = _runs(_jobs()["ttl"])
    match = re.search(r'if \[ "\$\{MODE\}" = "gate" \]; then ttl=(\d+); fi', script)
    assert match is not None
    assert GATE_MIN_TTL <= int(match.group(1)) <= 480


def test_never_reads_server_data_or_the_restore_environment() -> None:
    code = _code()
    assert "prod-restore-read" not in code
    assert "restore_source" not in code


def test_explore_is_still_a_fresh_boot_and_the_gate_phases_skip_for_it() -> None:
    jobs = _jobs()
    assert jobs["apply"]["if"] == "${{ inputs.mode == 'explore' }}"
    assert jobs["smoke"]["needs"] == "apply"
    assert "terraform_ref" not in jobs["apply"]["with"]
    assert "rollback" not in jobs["apply"]["with"]
    for name in ("baseline", "apply-baseline"):
        assert jobs[name]["if"] == "${{ inputs.mode == 'gate' }}"
    # Every other gate job hangs off a gate-only job, so it is skipped in explore.
    gate_roots = {"baseline", "apply-baseline"}
    for name in (
        "smoke-baseline",
        "seed",
        "detect",
        "writer-started",
        "writer",
        "apply-upgrade",
        "converge",
        "verify",
        "apply-rollback",
        "verify-rollback",
    ):
        assert _ancestors(jobs, name) & gate_roots, name


def test_ssh_jobs_use_the_drill_environment_and_shared_action() -> None:
    jobs = _jobs()
    for name in ("seed", "writer-started", "writer", "converge", "verify", "verify-rollback"):
        assert jobs[name]["environment"] == "drill", name
        assert any(s.get("uses") == "./.github/actions/drill-ssh" for s in jobs[name]["steps"])


# --- the marker script's in-place writer ------------------------------------------

STUB_DOCKER = """#!/bin/sh
# docker exec <container> python -c <code> [arg]: run the code locally on $REHEARSAL_DB.
[ "$1" = exec ] || exit 64
n=$(cat "$STUB_COUNT" 2>/dev/null || echo 0)
if [ -n "${STUB_STOP_AFTER:-}" ] && [ "$n" -ge "$STUB_STOP_AFTER" ]; then
  : > "$REHEARSAL_STOP_FILE"
fi
# A restarting app: every third insert fails.
if [ $((n % 3)) -eq 2 ]; then echo $((n + 1)) > "$STUB_COUNT"; exit 1; fi
echo $((n + 1)) > "$STUB_COUNT"
shift 2
code=$(printf '%s' "$3" | sed "s|/data/budget.db|$REHEARSAL_DB|")
shift 3
exec python3 -c "$code" "$@"
"""


@pytest.fixture
def host(tmp_path: Path) -> dict[str, str]:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    docker = bindir / "docker"
    docker.write_text(STUB_DOCKER)
    docker.chmod(0o755)
    return {
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "REHEARSAL_DB": str(tmp_path / "budget.db"),
        "REHEARSAL_STOP_FILE": str(tmp_path / "stop"),
        "STUB_COUNT": str(tmp_path / "count"),
    }


def _marker(env: dict[str, str], *args: str, **extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        ["/bin/sh", str(MARKER), *args],
        env={**env, **extra},
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_writer_until_survives_app_restarts_and_ends_on_stop(host: dict[str, str]) -> None:
    assert _marker(host, "init").returncode == 0
    res = _marker(host, "writer-until", "21", STUB_STOP_AFTER="6")

    assert res.returncode == 0
    lines = res.stdout.splitlines()
    assert lines[-1].startswith("writer stopped: requested before")
    committed = [ln for ln in lines if ln.startswith("committed ")]
    assert len(committed) >= 3
    # Failed inserts are retried with the same sequence number: no gaps.
    seqs = [int(ln.split()[1]) for ln in committed]
    assert seqs == list(range(21, 21 + len(seqs)))


def test_stop_creates_the_stop_file(host: dict[str, str]) -> None:
    assert not Path(host["REHEARSAL_STOP_FILE"]).exists()
    assert _marker(host, "stop").returncode == 0
    assert Path(host["REHEARSAL_STOP_FILE"]).exists()


# --- the seed-demo renderer ----------------------------------------------------------


def test_rendered_seed_demo_has_no_template_left_and_parses() -> None:
    res = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "scripts/ci/render_seed_demo.py"), "--hostname", "h.ts.net"],
        capture_output=True,
        text=True,
        check=True,
    )
    out = res.stdout
    assert "readonly COMPOSE_DIR='/etc/budget-planner'" in out
    assert "readonly READY_HOST='h.ts.net'" in out
    assert "$${" not in out
    assert not re.search(r"(?<!\$)\$\{(compose_dir|hostname)\}", out)
    check = subprocess.run(["bash", "-n"], input=out, text=True, capture_output=True, check=False)  # noqa: S607
    assert check.returncode == 0, check.stderr


def test_renderer_rejects_unsafe_values() -> None:
    res = subprocess.run(  # noqa: S603
        [sys.executable, str(ROOT / "scripts/ci/render_seed_demo.py"), "--hostname", "a b;rm"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 1
    assert "unsafe" in res.stderr
