"""ADR-0127 §7: replace-rehearsal.yml replays the T-D143 replacement on the drill. No network."""

from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "replace-rehearsal.yml"
ACTION = ROOT / ".github" / "actions" / "drill-ssh" / "action.yml"
MARKER = ROOT / "scripts" / "ci" / "rehearsal_marker.sh"
TERRAFORM = "./.github/workflows/terraform.yml"


def _wf() -> dict[Any, Any]:
    loaded: dict[Any, Any] = yaml.safe_load(WORKFLOW.read_text())
    return loaded


def _jobs() -> dict[str, Any]:
    jobs: dict[str, Any] = _wf()["jobs"]
    return jobs


def _needs(job: dict[str, Any]) -> set[str]:
    needs = job.get("needs") or []
    return {needs} if isinstance(needs, str) else set(needs)


def _runs(job: dict[str, Any]) -> str:
    return "\n".join(str(s.get("run", "")) for s in job.get("steps", []))


def test_dispatch_only_in_the_drill_group() -> None:
    wf = _wf()
    assert wf[True] == {"workflow_dispatch": {}}  # PyYAML reads `on:` as True
    assert wf["concurrency"] == {"group": "drill", "cancel-in-progress": False}


def test_every_apply_is_a_drill_apply_with_the_rehearsal_knobs() -> None:
    jobs = _jobs()
    applies = {k: j for k, j in jobs.items() if j.get("uses") == TERRAFORM}
    assert set(applies) == {"apply-empty", "apply-seed", "apply-replace", "teardown"}
    assert all(j["with"]["env"] == "drill" for j in applies.values())

    empty, seed, replace = (
        applies[k]["with"] for k in ("apply-empty", "apply-seed", "apply-replace")
    )
    assert empty["drill_allow_empty_db"] == "false"
    assert empty["drill_root_volume_type"] == "sbs_volume"
    assert "reuse_drill_run_id" not in empty
    assert "drill_allow_empty_db" not in seed  # default "true"
    assert seed["drill_root_volume_type"] == "sbs_volume" and seed["reuse_drill_run_id"] is True
    # The T-D143 transition: Block Storage -> l_ssd on the same drill.
    assert replace["drill_root_volume_type"] == "l_ssd" and replace["reuse_drill_run_id"] is True


def test_phases_run_in_order_and_replace_starts_under_load() -> None:
    jobs = _jobs()
    assert "check-empty" in _needs(jobs["apply-seed"])
    assert _needs(jobs["seed"]) == {"apply-seed"}
    assert _needs(jobs["writer"]) == {"seed"}
    assert _needs(jobs["writer-started"]) == {"seed"}
    assert "writer-started" in _needs(jobs["apply-replace"])
    assert {"seed", "writer", "apply-replace"} <= _needs(jobs["verify"])


def test_detection_is_checked_both_ways() -> None:
    jobs = _jobs()
    seed = jobs["seed"]["steps"]
    verify = jobs["verify"]["steps"]
    assert any(
        s.get("env", {}).get("REPLACED") == "${{ needs.apply-seed.outputs.server_replaced }}"
        and 'test "${REPLACED}" = "false"' in s["run"]
        for s in seed
    )
    assert any(
        s.get("env", {}).get("REPLACED") == "${{ needs.apply-replace.outputs.server_replaced }}"
        and 'test "${REPLACED}" = "true"' in s["run"]
        for s in verify
    )


def test_checks_cover_guard_restore_flush_and_integrity() -> None:
    jobs = _jobs()
    assert "refusing to start empty" in _runs(jobs["check-empty"])
    verify = _runs(jobs["verify"])
    assert "--require-restore" in verify
    assert '.result == "restored" and .generation == $gen' in verify
    assert 'if [ "${max}" -lt "${WRITER_LAST}" ]' in verify
    assert "PRAGMA integrity_check" in verify
    assert "--replaced-name" in verify and "--require" in verify
    # Review findings: the old node never counts as settled, and the writer must
    # have ended because the old host went away.
    assert '--created-after "${CREATED_AFTER}"' in verify
    assert (
        jobs["verify"]["steps"][2]["env"]["CREATED_AFTER"]
        == "${{ needs.writer-started.outputs.at }}"
    )
    writer = _runs(jobs["writer"])
    assert "^writer stopped: app gone" in writer and '"${rc}" != 255' in writer
    assert jobs["verify"]["env"]["SEED_GENERATION"] == "${{ needs.seed.outputs.generation }}"
    assert jobs["verify"]["env"]["WRITER_LAST"] == "${{ needs.writer.outputs.last }}"


def test_teardown_always_runs_after_every_phase() -> None:
    jobs = _jobs()
    teardown = jobs["teardown"]
    assert teardown["with"]["destroy"] is True
    assert (
        "always()" in teardown["if"] and "needs.apply-empty.result != 'skipped'" in teardown["if"]
    )
    phases = set(jobs) - {"drill-lock", "image", "teardown", "tailnet-cleanup"}
    assert phases <= _needs(teardown)


def test_ssh_jobs_use_the_drill_environment_and_shared_action() -> None:
    jobs = _jobs()
    for name in ("check-empty", "seed", "writer-started", "writer", "verify"):
        job = jobs[name]
        assert job["environment"] == "drill", name
        assert any(s.get("uses") == "./.github/actions/drill-ssh" for s in job["steps"]), name


def test_actions_are_pinned_by_sha() -> None:
    texts = [WORKFLOW.read_text(), ACTION.read_text()]
    for text in texts:
        for line in text.splitlines():
            stripped = line.strip().removeprefix("- ")
            if stripped.startswith("uses:") and "./" not in stripped:
                ref = stripped.split("@", 1)[1].split()[0]
                assert len(ref) == 40, line


# --- the marker script, against a stub docker and a temp DB ---------------------

STUB_DOCKER = """#!/bin/sh
# docker exec <container> python -c <code> [arg]: run the code locally on $REHEARSAL_DB.
# docker inspect: "true" while $STUB_RUNNING exists.
if [ "$1" = inspect ]; then
  if [ -e "$STUB_RUNNING" ]; then echo true; else echo false; fi
  exit 0
fi
[ "$1" = exec ] || exit 64
if [ -n "${STUB_FLAKY:-}" ] && [ ! -e "$STUB_FLAKY" ]; then : > "$STUB_FLAKY"; exit 1; fi
n=$(cat "$STUB_COUNT" 2>/dev/null || echo 0)
# At the limit "the app container stops": the insert fails and inspect says false.
if [ -n "${STUB_FAIL_AFTER:-}" ] && [ "$n" -ge "$STUB_FAIL_AFTER" ]; then
  rm -f "$STUB_RUNNING"
  exit 1
fi
echo $((n + 1)) > "$STUB_COUNT"
shift 2
[ "$1" = python ] && [ "$2" = -c ] || exit 65
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
        "STUB_COUNT": str(tmp_path / "count"),
        "STUB_RUNNING": str(tmp_path / "running"),
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


def test_init_write_and_stats(host: dict[str, str]) -> None:
    assert _marker(host, "init").returncode == 0
    assert _marker(host, "init").returncode == 0  # idempotent
    assert _marker(host, "write", "3").stdout.strip() == "wrote 1..3"

    assert _marker(host, "stats").stdout.strip() == "3|3"


def test_writer_reports_each_commit_and_stops_when_the_app_is_gone(host: dict[str, str]) -> None:
    _marker(host, "init")
    Path(host["STUB_COUNT"]).write_text("0")

    # init used no count; allow 2 more inserts, then "the container stopped".
    res = _marker(host, "writer", "21", STUB_FAIL_AFTER="2")

    assert res.returncode == 0
    assert res.stdout.splitlines() == [
        "committed 21",
        "committed 22",
        "writer stopped: app gone before 23",
    ]
    with sqlite3.connect(host["REHEARSAL_DB"]) as db:
        assert db.execute("SELECT group_concat(seq) FROM t_d156_marker").fetchone() == ("21,22",)


def test_unknown_command_is_an_error(host: dict[str, str]) -> None:
    assert _marker(host, "drop").returncode == 2


def test_writer_retries_a_failed_insert_while_the_app_runs(
    host: dict[str, str], tmp_path: Path
) -> None:
    """A transient failure (e.g. `database is locked`) must not end the writer early."""
    _marker(host, "init")
    Path(host["STUB_COUNT"]).write_text("0")
    Path(host["STUB_RUNNING"]).touch()

    # The first insert fails once while the app runs: retried, not the end.
    res = _marker(host, "writer", "21", STUB_FAIL_AFTER="2", STUB_FLAKY=str(tmp_path / "flaky"))

    assert res.stdout.splitlines() == [
        "committed 21",
        "committed 22",
        "writer stopped: app gone before 23",
    ]
