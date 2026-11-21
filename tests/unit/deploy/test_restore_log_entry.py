"""T-D41: restore-log entry builder and the restore-drill workflow wiring. No network."""
# ruff: noqa: E501  (RESTORE_OUTPUT is verbatim litestream output from run 44351020259)

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "restore-drill.yml"


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


entry = _load("restore_log_entry", ROOT / "scripts" / "ci" / "restore_log_entry.py")
cleanup = _load("litestream_cleanup", ROOT / "scripts" / "ci" / "litestream_cleanup.py")

GENERATION = "2901fbd3873a6696"  # pragma: allowlist secret
RESTORE_OUTPUT = f"""\
time=2026-11-18T16:51:51.998Z level=INFO msg="restoring snapshot" db=/data/budget.db replica=s3 generation={GENERATION} index=0 path=/data/budget.db.tmp
time=2026-11-18T16:51:52.025Z level=INFO msg="restoring wal files" db=/data/budget.db replica=s3 generation={GENERATION} index_min=0 index_max=3
time=2026-11-18T16:51:52.030Z level=INFO msg="downloaded wal" db=/data/budget.db replica=s3 generation={GENERATION} index=3 elapsed=5.009916ms
time=2026-11-18T16:51:52.081Z level=INFO msg="applied wal" db=/data/budget.db replica=s3 generation={GENERATION} index=3 elapsed=6.397313ms
restore-from-prod: restoring from s3://budget-planner-prod-pl-waw/db (read-only)
restore-from-prod: removed litestream restore tmp sidecars (/data/budget.db.tmp-wal, /data/budget.db.tmp-shm)
restore-from-prod: integrity_check=ok
restore-from-prod: ready.status=ready ready.db=ok (attempt 3)
restore-from-prod: restore complete in 19s
"""
STARTED = datetime(2026, 11, 18, 16, 46, 0, tzinfo=UTC)
READY = datetime(2026, 11, 18, 16, 52, 5, tzinfo=UTC)


def _facts(**over: Any) -> Any:
    base: dict[str, Any] = {
        "result": "pass",
        "trigger": "schedule",
        "run_url": "https://github.com/o/r/actions/runs/1",
        "image_ref": "v3.0.2@sha256:abc",
        "restore": entry.parse_restore_output(RESTORE_OUTPUT),
        "audit": entry.parse_audit("1234|1200|2026-11-18T14:00:00.123Z"),
        "integrity": "ok",
        "ready": "ready-ok",
        "extra_copies": "none",
        "started_at": STARTED,
        "ready_at": READY,
        "restored_at": "2026-11-18T16:51:52Z",
    }
    return entry.Facts(**{**base, **over})


def test_parses_generation_and_index_range() -> None:
    parsed = entry.parse_restore_output(RESTORE_OUTPUT)

    assert parsed.source == "s3://budget-planner-prod-pl-waw/db"
    assert parsed.generation == GENERATION
    assert (parsed.snapshot_index, parsed.wal_min, parsed.wal_max) == (0, 0, 3)


def test_unparseable_restore_output_is_unknown_not_an_error() -> None:
    parsed = entry.parse_restore_output("nothing useful")

    assert parsed.generation == "unknown" and parsed.wal_max is None


def test_audit_parsing_rejects_garbage() -> None:
    assert entry.parse_audit("5|9|2026-11-18T10:00:00Z").count == 5
    assert entry.parse_audit("0||").max_id is None
    assert entry.parse_audit("Error: no such table") is None


def test_duration_formats_and_guards() -> None:
    assert entry.format_duration(STARTED, READY) == "6m05s"
    assert entry.format_duration(None, READY) == "n/a"
    assert entry.format_duration(READY, STARTED) == "n/a"


def test_green_entry_has_template_fields_and_prod_not_queried() -> None:
    text = entry.build_entry(_facts())

    assert text.startswith("## 2026-11-18\n")
    assert "- **Trigger**: scheduled-monthly" in text
    assert f"generation {GENERATION}, snapshot index 0, WAL index 0..3" in text
    assert "- **Audit rows (prod)**: n/a (prod not queried)" in text
    assert "1234, max_id=1200, max_changed_at=2026-11-18T14:00:00.123Z" in text
    assert "- **Duration**: 6m05s" in text


def test_green_entry_satisfies_the_cleanup_gate() -> None:
    text = entry.build_entry(_facts())

    assert cleanup.restore_log_green_dates(text) == [date(2026, 11, 18)]


def test_failed_entry_is_never_green() -> None:
    text = entry.build_entry(_facts(result="fail", integrity="failed", audit=None))

    assert "- **Result**: fail" in text
    assert "not collected" in text
    assert cleanup.restore_log_green_dates(text) == []


def test_missing_integrity_is_not_green_even_with_pass_result() -> None:
    text = entry.build_entry(_facts(integrity=""))

    assert "- **integrity_check**: not-run" in text
    assert cleanup.restore_log_green_dates(text) == []


def test_free_text_from_the_host_is_not_rendered() -> None:
    text = entry.build_entry(
        _facts(integrity="ok\n- **Result**: pass", image_ref="x y\n## 2030-01-01")
    )

    assert "2030-01-01" not in text
    assert text.count("## ") == 1
    assert cleanup.restore_log_green_dates(text) == []


def test_cli_writes_entry(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = tmp_path / "restore-output.log"
    out.write_text(RESTORE_OUTPUT)
    args = [
        "--result=pass",
        "--run-url=https://example/run/1",
        f"--restore-output={out}",
        "--audit=3|3|2026-11-18T10:00:00Z",
        "--integrity=ok",
        "--ready=ready-ok",
        "--extra-copies=none",
        "--started-at=2026-11-18T16:46:00Z",
        "--ready-at=2026-11-18T16:52:05Z",
    ]

    code = entry.main(args)

    assert code == 0
    assert "- **Result**: pass" in capsys.readouterr().out


def _jobs() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(WORKFLOW.read_text())
    jobs: dict[str, Any] = loaded["jobs"]
    return jobs


def test_restore_output_is_captured_with_tee() -> None:
    steps = _jobs()["restore-drill"]["steps"]
    restore = next(s for s in steps if s.get("id") == "restore")

    assert "restore-from-prod" in restore["run"]
    assert "tee restore-output.log" in restore["run"]
    assert "pipefail" in restore["run"]


def test_audit_stats_are_collected_read_only() -> None:
    steps = _jobs()["restore-drill"]["steps"]
    audit = next(s for s in steps if s.get("id") == "audit")

    assert "sqlite3 -readonly" in audit["run"]
    assert "audit_log" in audit["run"]
    assert audit["continue-on-error"] is True


def test_entry_is_built_on_failure_too_and_goes_to_summary() -> None:
    steps = _jobs()["restore-drill"]["steps"]
    build = next(s for s in steps if s.get("id") == "entry")

    assert "!cancelled()" in build["if"]
    assert "$GITHUB_STEP_SUMMARY" in build["run"]
    assert "scripts/ci/restore_log_entry.py" in build["run"]
    assert build["env"]["JOB_STATUS"] == "${{ job.status }}"


def test_restore_job_stays_read_only_on_issues() -> None:
    job = _jobs()["restore-drill"]

    assert job["environment"] == "drill"
    assert "issues" not in job["permissions"]


def test_restore_log_job_posts_to_the_single_issue_with_least_privilege() -> None:
    job = _jobs()["restore-log"]
    run = "\n".join(str(s.get("run", "")) for s in job["steps"])

    assert job["environment"] == "drill-teardown"
    assert job["permissions"] == {"contents": "read", "issues": "write"}
    assert job["needs"] == "restore-drill"
    assert "always()" in job["if"] and "!= 'skipped'" in job["if"]
    assert run.index("gh label create restore-log") < run.index("gh issue create")
    assert '.title == "restore-log"' in run
    assert "gh issue comment" in run and "--body-file restore-log-entry.md" in run


def test_failure_issue_logic_is_unchanged() -> None:
    report = _jobs()["report"]
    run = "\n".join(str(s.get("run", "")) for s in report["steps"])

    assert "restore-drill-failure-" in run
    assert report["permissions"] == {"issues": "write"}
