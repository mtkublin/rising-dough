"""Claude Code hook guard for orchestrated runs (T-Q331, ADR-0150 amendment 2026-11-25)."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("agent_guard", ROOT / "scripts/ci/agent_guard.py")
assert _spec is not None and _spec.loader is not None
guard = importlib.util.module_from_spec(_spec)
sys.modules["agent_guard"] = guard
_spec.loader.exec_module(guard)

FRESH = guard.AgentState()
UNIT = "uv run pytest tests/unit/test_a.py -q --no-cov -p no:xdist"
E2E_FILE = "uv run pytest tests/e2e/test_today_journey.py -q --no-cov"


def _deny(role: str, command: str, background: bool = False, state: object = FRESH) -> str | None:
    reason: str | None = guard.decide_pre(role, command, background, state).reason
    return reason


@pytest.mark.parametrize(
    ("segment", "kind"),
    [
        (UNIT, "file"),
        ("python -m pytest tests/unit/test_a.py::test_x", "file"),
        ("uv run pytest tests/architecture -q", "file"),
        ("uv run pytest tests/ui_map/ -q", "file"),
        ("just guards", "file"),
        (E2E_FILE, "e2e-file"),
        ("just test-e2e tests/e2e/test_a.py -x", "e2e-file"),
        ("uv run pytest tests/e2e -q", "e2e-suite"),
        ("just test-e2e", "e2e-suite"),
        ("just test-e2e -k journey", "e2e-suite"),
        ("just visual", "e2e-suite"),
        ("uv run pytest tests/integration -k fx", "dir"),
        ("uv run pytest tests/unit/test_a.py tests/contract", "dir"),
        ("uv run pytest -q", "full"),
        ("uv run pytest tests/unit/a.py > /tmp/o.txt", "file"),
        ("uv run pytest tests/unit/a.py >/tmp/o.txt 2>&1", "file"),
        ("cd x && uv run pytest tests/unit/a.py", "file"),
        ("uv run pytest tests/integration 2>&1", "dir"),
        ("PYTEST_WORKERS=2 just test-changed abc123", "full"),
        ("just ci", "full"),
        ("git status --short", None),
        ("just check-item UR09a 'src/*'", None),
    ],
)
def test_run_kind(segment: str, kind: str | None) -> None:
    assert guard.run_kind(segment) == kind


@pytest.mark.parametrize(
    ("segment", "too_many"),
    [
        ("uv run pytest tests -n auto", True),
        ("uv run pytest tests -n4", True),
        ("uv run pytest tests --numprocesses=8", True),
        ("uv run pytest tests -n 2", False),
        ("uv run pytest tests/unit/test_a.py -p no:xdist", False),
        ("echo -n auto", False),
    ],
)
def test_worker_cap(segment: str, too_many: bool) -> None:
    assert guard.too_many_workers(segment) is too_many


def test_heredoc_body_is_not_a_command() -> None:
    command = "cat > notes.md <<'EOF'\nrun uv run pytest tests/e2e -n auto\nEOF\ngit add notes.md"
    assert guard.strip_heredocs(command) == "cat > notes.md <<'EOF'\ngit add notes.md"
    assert _deny("implementer", command) is None


def test_main_thread_and_other_agents_are_untouched() -> None:
    assert _deny("", "just ci") is None
    assert guard.decide_pre(None, "until mkdir /tmp/x.lock; do sleep 20; done", False, FRESH) == (
        guard.Decision(None)
    )
    assert _deny("Explore", "uv run pytest -n auto") is None


def test_implementer_scope() -> None:
    assert _deny("implementer", UNIT) is None
    assert _deny("implementer", "cd /wt && PYTEST_WORKERS=2 just test-changed main") == (
        "agent_guard: implementer may not run this: the full test suite is the wave tester's "
        "job (ADR-0150)."
    )
    assert _deny("implementer", "uv run pytest tests/integration -q") == (
        "agent_guard: implementer may not run this: directory runs are the wave tester's job; "
        "run the single test files your brief names (ADR-0150)."
    )
    assert _deny("implementer", "uv run pytest tests/e2e -q") == (
        "agent_guard: implementer may not run this: the e2e/visual suite is the wave tester's "
        "job (or e2e.yml on a pushed branch) (ADR-0150)."
    )


def test_implementer_e2e_files_are_budgeted() -> None:
    first = guard.decide_pre("implementer", E2E_FILE, False, FRESH)
    assert first == guard.Decision(None, counts_e2e=True)
    spent = guard.AgentState(e2e_runs=4)
    assert _deny("implementer", E2E_FILE, state=spent) == (
        "agent_guard: local e2e budget spent (4 runs). Commit, push your wi/** branch and read "
        "the e2e.yml run on it (gh run list --branch <branch>, then gh run watch in the "
        "background). The wave tester runs the e2e suite after merge."
    )


def test_reviewer_runs_single_unit_files_only() -> None:
    assert _deny("reviewer", UNIT) is None
    assert _deny("reviewer", E2E_FILE) == (
        "agent_guard: reviewer may not run this: e2e evidence comes from the e2e.yml run on "
        "the pushed wi/** branch (ADR-0150)."
    )
    assert _deny("reviewer", "uv run pytest tests/contract -q") is not None
    assert _deny("visual-auditor", "just test-e2e") is not None
    assert _deny("scribe", "just test") is not None


def test_tester_runs_suites() -> None:
    assert _deny("tester", "PYTEST_WORKERS=2 just test-changed abc", background=True) is None
    assert _deny("tester", "PYTEST_WORKERS=2 just test-e2e", background=True) is None
    assert _deny("tester", "uv run pytest tests -n auto") == guard.WORKERS_REASON


@pytest.mark.parametrize(
    "command",
    [
        "until mkdir /tmp/ui-redesign-heavy.lock 2>/dev/null; do sleep 20; done",
        "while ! grep -q passed out.log; do sleep 5; done",
        "sleep 60",
        "gh run watch 45452392502 --exit-status",
    ],
)
def test_foreground_waits_are_denied(command: str) -> None:
    assert _deny("tester", command) == guard.WAIT_REASON
    assert _deny("tester", command, background=True) is None


def test_short_sleep_is_allowed() -> None:
    assert _deny("implementer", "sleep 10; curl -s localhost:8000/health") is None


def test_runtime_budget_blocks_heavy_work_only() -> None:
    over = guard.AgentState(active_s=61 * 60)
    assert _deny("implementer", UNIT, state=over) == (
        "agent_guard: the implementer runtime budget (60 min of active time) is spent. No more "
        "test runs, locks or audits: commit what is green and report now (STATUS: PARTIAL with "
        "the rest under LEFT)."
    )
    assert _deny("implementer", "mkdir /tmp/ui-redesign-heavy.lock", state=over) is not None
    assert _deny("implementer", "git commit -F msg.txt", state=over) is None
    reviewer = guard.AgentState(active_s=31 * 60)
    assert "reviewer runtime budget (30 min" in str(_deny("reviewer", UNIT, state=reviewer))
    assert _deny("implementer", UNIT, state=guard.AgentState(active_s=59 * 60)) is None


def test_active_time_caps_idle_gaps() -> None:
    first = guard.advance(FRESH, 1000.0)
    assert first == guard.AgentState(active_s=0.0, last=1000.0)
    busy = guard.advance(first, 1300.0)
    assert busy == guard.AgentState(active_s=300.0, last=1300.0)
    parked = guard.advance(busy, 1300.0 + 3 * 3600)
    assert parked.active_s == 300.0 + 15 * 60


def test_run_pre_persists_state_and_denies_as_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    payload = {
        "session_id": "s1",
        "agent_id": "a1",
        "agent_type": "implementer",
        "tool_name": "Bash",
        "tool_input": {"command": E2E_FILE},
    }
    for now in (100.0, 160.0, 220.0, 280.0):
        assert guard.run_pre(payload, now) is None
    state = json.loads((tmp_path / "agent-guard/s1/a1.json").read_text())
    assert state == {"active_s": 180.0, "last": 280.0, "e2e_runs": 4}
    out = guard.run_pre(payload, 300.0)
    assert out == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": guard.E2E_BUDGET_REASON.format(n=4),
        }
    }
    other = {**payload, "tool_name": "Read"}
    assert guard.run_pre(other, 400.0) is None


def _skill_record(path: str) -> dict[str, object]:
    text = f"Base directory for this skill: {path}\n\n# Skill"
    return {"type": "user", "message": {"role": "user", "content": text}}


def test_skill_load_detection() -> None:
    assert guard.is_skill_load(_skill_record("/r/.claude/skills/orchestrator-mode")) is True
    assert guard.is_skill_load(_skill_record("/r/.claude/skills/frontend-visual-audit")) is False
    quoted = {
        "type": "user",
        "message": {
            "content": [
                {"type": "tool_result", "content": "Base directory for this skill: "},
            ]
        },
    }
    assert guard.is_skill_load(quoted) is False


def test_stop_decision() -> None:
    assert guard.decide_stop(False, False, "done for now") is None
    assert guard.decide_stop(True, True, "done for now") is None
    assert guard.decide_stop(True, False, "Merged UR04g.") == guard.STOP_REASON
    assert guard.decide_stop(True, False, "Merged UR04g.\nRUN-STATE: waiting UR09a, UR10b") is None
    assert guard.decide_stop(True, False, "RUN-STATE: maybe") == guard.STOP_REASON


def _transcript(tmp_path: Path, records: list[dict[str, object]]) -> Path:
    path = tmp_path / "t.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in records))
    return path


def _assistant(text: str) -> dict[str, object]:
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def test_run_stop_reads_the_transcript(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    records = [_skill_record("/r/.claude/skills/orchestrator-mode"), _assistant("Merged UR04g.")]
    path = _transcript(tmp_path, records)
    payload = {"session_id": "s2", "transcript_path": str(path)}
    assert guard.run_stop(payload) == guard.STOP_REASON
    assert guard.run_stop({**payload, "last_assistant_message": "RUN-STATE: done"}) is None
    assert guard.run_stop({**payload, "agent_type": "implementer"}) is None
    empty = tmp_path / "plain"
    empty.mkdir()
    plain = _transcript(empty, [_assistant("Merged UR04g.")])
    assert guard.run_stop({"session_id": "s3", "transcript_path": str(plain)}) is None


def test_main_blocks_stop_with_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    path = _transcript(tmp_path, [_skill_record("/r/.claude/skills/orchestrator-mode")])
    payload = {"session_id": "s4", "transcript_path": str(path), "last_assistant_message": "ok"}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert guard.main(["agent_guard.py", "stop"]) == 2
    assert capsys.readouterr().err == guard.STOP_REASON + "\n"


def test_main_fails_open(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("{not json"))
    assert guard.main(["agent_guard.py", "pre-tool"]) == 0
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("command", "kind"),
    [
        ("uv run pytest tests/unit/a.py -p no:xdist 2>&1 | tail -5", "file"),
        ("uv run pytest 2>&1 | tail -20", "full"),
        ("uv run pytest tests/unit/a.py; uv run pytest", "full"),
        ("uv run pytest tests/unit/a.py & uv run pytest tests/integration", "dir"),
        ("cd x && uv run pytest tests/unit/a.py 2>&1 | tail -3", "file"),
    ],
)
def test_chain_kind(command: str, kind: str) -> None:
    parts = guard.segments(command)
    assert guard.worst(k for k in (guard.run_kind(p) for p in parts) if k) == kind
