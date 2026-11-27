"""Claude Code hook guard for orchestrated runs (ADR-0150 amendment 2026-11-25, T-Q331).

Two modes, wired in ``.claude/settings.json``; the hook JSON arrives on stdin.

``pre-tool`` (PreToolUse, Bash): acts only when ``agent_type`` is one of the six role agents
(``.claude/agents/``). Denies, with a reason the agent sees: out-of-scope test runs per role,
``-n auto``, foreground waits, local e2e runs past the implementer budget, and heavy work past the
role's runtime budget. The main thread and other agents pass untouched.

``stop`` (Stop): acts only in a session that loaded the ``orchestrator-mode`` skill. Refuses, once,
a stop whose last message has no ``RUN-STATE:`` line.

The decisions are pure functions; ``main`` does the I/O. Any error allows the call (fail open):
a broken guard must never stop every agent. Command matching is a guardrail, not a security
boundary.

Usage: agent_guard.py pre-tool|stop   (hook JSON on stdin)
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
import tempfile
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path

ROLES = frozenset({"implementer", "reviewer", "tester", "visual-auditor", "scribe", "explorer"})
BUDGET_MIN = {
    "implementer": 60,
    "tester": 60,
    "visual-auditor": 45,
    "reviewer": 30,
    "scribe": 20,
    "explorer": 20,
}
E2E_LOCAL_BUDGET = 4  # local e2e-file runs per implementer, then e2e.yml on the pushed branch
IDLE_CAP_S = 15 * 60  # an idle gap counts at most this much active time
MAX_FG_SLEEP_S = 30
MAX_WORKERS = 2
SMALL_DIRS = ("tests/architecture", "tests/ui_map")  # cheap directory runs, treated as files
STATE_DIR = "agent-guard"
SKILL_MARKER = "Base directory for this skill:"
ORCHESTRATOR_SKILL = "/.claude/skills/orchestrator-mode"
TAIL_BYTES = 2_000_000

# Test-run kinds, worst first.
FULL, E2E_SUITE, DIR, E2E_FILE, FILE = "full", "e2e-suite", "dir", "e2e-file", "file"
_RANK = (FULL, E2E_SUITE, DIR, E2E_FILE, FILE)
_FULL_RECIPES = frozenset({"test", "test-changed", "test-fast", "ci", "mutate"})
_E2E_SUITE_RECIPES = frozenset({"test-e2e-browsers", "visual", "visual-update", "test-visual"})
_FILE_RECIPES = frozenset({"guards"})
_VALUE_OPTS = frozenset(
    {
        "-k", "-m", "-p", "-n", "-c", "-o", "-W", "--maxfail", "--deselect", "--ignore",
        "--rootdir", "--override-ini", "--junitxml", "--basetemp", "--db", "--e2e-browser",
        "--tb", "--durations", "--cov", "--cov-report", "--numprocesses", "--dist",
    }
)  # fmt: skip
_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
_SPLIT = re.compile(r"\|\||&&|(?<![<>&])&(?![>&])|;|\||\n")
_REDIR = re.compile(r"^(?:\d*|&)(?:>>?|<)(?P<target>.*)$")
_LOOP_WAIT = re.compile(r"\b(until|while)\b.*?\bdo\b.*?\bsleep\b", re.S)
_SLEEP = re.compile(r"\bsleep\s+(\d+)")
_GH_WATCH = re.compile(r"\bgh\s+run\s+watch\b")
_LOCK = re.compile(r"\bmkdir\s+(-p\s+)?\S*\.lock\b")
_AUDIT = re.compile(r"audit_frontend\.py|\bplaywright\b")
RUN_STATE = re.compile(r"^RUN-STATE: (waiting|question|blocked|paused|done)\b", re.M)

WAIT_REASON = (
    "agent_guard: foreground waits are not allowed for role agents (ADR-0150 amendment "
    "2026-11-25 §2). Run the wait or watch with run_in_background: true; you are re-invoked "
    "when it exits. This avoids the 10-minute Bash cap and keeps the lock queue moving."
)
WORKERS_REASON = (
    "agent_guard: pytest with more than 2 workers or -n auto is not allowed (ADR-0150 §6). "
    "Use -p no:xdist for single files; the wave tester uses PYTEST_WORKERS=2."
)
E2E_BUDGET_REASON = (
    "agent_guard: local e2e budget spent ({n} runs). Commit, push your wi/** branch and read "
    "the e2e.yml run on it (gh run list --branch <branch>, then gh run watch in the "
    "background). The wave tester runs the e2e suite after merge."
)
BUDGET_REASON = (
    "agent_guard: the {role} runtime budget ({minutes} min of active time) is spent. No more "
    "test runs, locks or audits: commit what is green and report now ({report})."
)
STOP_REASON = (
    "agent_guard: an orchestrator turn must end with one line "
    "'RUN-STATE: waiting <what> | question <for the operator> | blocked <why> | paused | done' "
    "(ADR-0150 amendment 2026-11-25 §4). If work is unblocked (finished reports to act on, "
    "items to merge or dispatch), do it now instead of stopping. If you wait, keep the "
    "background heartbeat running."
)
_SCOPE_REASON = {
    FULL: "the full test suite is the wave tester's job",
    E2E_SUITE: "the e2e/visual suite is the wave tester's job (or e2e.yml on a pushed branch)",
    DIR: "directory runs are the wave tester's job; run the single test files your brief names",
    E2E_FILE: "e2e evidence comes from the e2e.yml run on the pushed wi/** branch",
}
_REPORT = {
    "implementer": "STATUS: PARTIAL with the rest under LEFT",
    "reviewer": "your verdict with the checks done so far",
    "visual-auditor": "STATUS: BLOCKED with what was audited",
    "tester": "STATUS: BLOCKED with the runs done so far",
}
# Kinds each role may run locally (E2E_FILE for the implementer is also budgeted).
_ALLOWED = {
    "implementer": frozenset({FILE, E2E_FILE}),
    "tester": frozenset(_RANK),
}
_DEFAULT_ALLOWED = frozenset({FILE})


@dataclass(frozen=True)
class AgentState:
    active_s: float = 0.0
    last: float | None = None
    e2e_runs: int = 0


@dataclass(frozen=True)
class Decision:
    reason: str | None  # None allows the call
    counts_e2e: bool = False


def strip_heredocs(command: str) -> str:
    """Drop heredoc bodies: writing a file that mentions pytest is not a test run."""
    out: list[str] = []
    delimiter: str | None = None
    for line in command.split("\n"):
        if delimiter is not None:
            if line.strip() == delimiter:
                delimiter = None
            continue
        out.append(line)
        found = _HEREDOC.search(line)
        if found:
            delimiter = found.group(2)
    return "\n".join(out)


def segments(command: str) -> list[str]:
    return [s.strip() for s in _SPLIT.split(command) if s.strip()]


def _tokens(segment: str) -> list[str]:
    try:
        tokens = shlex.split(segment)
    except ValueError:
        tokens = segment.split()
    while tokens and _ENV.match(tokens[0]):
        tokens = tokens[1:]
    return _drop_redirects(tokens)


def _drop_redirects(tokens: Sequence[str]) -> list[str]:
    """Remove `>`, `>>`, `<`, `2>&1`, `&>` and their target words: they are not arguments."""
    kept: list[str] = []
    skip = False
    for word in tokens:
        if skip:
            skip = False
            continue
        found = _REDIR.match(word)
        if found is None:
            kept.append(word)
        elif not found.group("target"):
            skip = True  # target is the next word
    return kept


def _pytest_args(tokens: Sequence[str]) -> list[str] | None:
    for i, word in enumerate(tokens):
        if word == "pytest" or word.endswith("/pytest"):
            return list(tokens[i + 1 :])
        if word == "-m" and i + 1 < len(tokens) and tokens[i + 1] == "pytest":
            return list(tokens[i + 2 :])
    return None


def _paths(args: Sequence[str]) -> list[str]:
    paths: list[str] = []
    skip = False
    for arg in args:
        if skip:
            skip = False
        elif arg in _VALUE_OPTS:
            skip = True
        elif not arg.startswith("-"):
            paths.append(arg)
    return paths


def _path_kind(path: str) -> str:
    target = path.split("::", maxsplit=1)[0].rstrip("/")
    e2e = target == "tests/e2e" or target.startswith("tests/e2e/")
    if target.endswith(".py"):
        return E2E_FILE if e2e else FILE
    if e2e:
        return E2E_SUITE
    small = any(target == d or target.startswith(d + "/") for d in SMALL_DIRS)
    return FILE if small else DIR


def worst(kinds: Iterable[str]) -> str | None:
    ranked = sorted(kinds, key=_RANK.index)
    return ranked[0] if ranked else None


def _just_kind(tokens: Sequence[str]) -> str | None:
    recipe = tokens[1] if len(tokens) > 1 else ""
    if recipe in _FULL_RECIPES:
        return FULL
    if recipe in _E2E_SUITE_RECIPES:
        return E2E_SUITE
    if recipe in _FILE_RECIPES:
        return FILE
    if recipe == "test-e2e":
        files = [p for p in _paths(tokens[2:]) if _path_kind(p) == E2E_FILE]
        return E2E_FILE if files and len(files) == len(_paths(tokens[2:])) else E2E_SUITE
    return None


def run_kind(segment: str) -> str | None:
    """The kind of test run one command segment starts, or None."""
    tokens = _tokens(segment)
    if tokens[:1] == ["just"]:
        return _just_kind(tokens)
    args = _pytest_args(tokens)
    if args is None:
        return None
    paths = _paths(args)
    if not paths:
        return FULL
    return worst(_path_kind(p) for p in paths)


def too_many_workers(segment: str) -> bool:
    args = _pytest_args(_tokens(segment))
    if args is None:
        return False
    for i, arg in enumerate(args):
        value: str | None = None
        if arg in ("-n", "--numprocesses") and i + 1 < len(args):
            value = args[i + 1]
        elif arg.startswith(("-n=", "--numprocesses=")):
            value = arg.split("=", 1)[1]
        elif arg.startswith("-n") and len(arg) > len("-n") and not arg.startswith("-n="):
            value = arg[2:]
        if value is not None and not (value.isdigit() and int(value) <= MAX_WORKERS):
            return True
    return False


def foreground_wait(text: str) -> bool:
    if _LOOP_WAIT.search(text) or _GH_WATCH.search(text):
        return True
    return any(int(s) > MAX_FG_SLEEP_S for s in _SLEEP.findall(text))


def advance(state: AgentState, now: float) -> AgentState:
    """Add the time since the agent's last Bash call, an idle gap capped at IDLE_CAP_S."""
    if state.last is None:
        return replace(state, last=now)
    gap = min(max(now - state.last, 0.0), IDLE_CAP_S)
    return replace(state, active_s=state.active_s + gap, last=now)


def _scope(role: str, kind: str, state: AgentState) -> Decision:
    allowed = _ALLOWED.get(role, _DEFAULT_ALLOWED)
    if kind not in allowed:
        return Decision(f"agent_guard: {role} may not run this: {_SCOPE_REASON[kind]} (ADR-0150).")
    if role == "implementer" and kind == E2E_FILE:
        if state.e2e_runs >= E2E_LOCAL_BUDGET:
            return Decision(E2E_BUDGET_REASON.format(n=state.e2e_runs))
        return Decision(None, counts_e2e=True)
    return Decision(None)


def decide_pre(role: str | None, command: str, background: bool, state: AgentState) -> Decision:
    """PreToolUse decision for one Bash call of a role agent."""
    if role not in ROLES:
        return Decision(None)
    text = strip_heredocs(command)
    parts = segments(text)
    if any(too_many_workers(p) for p in parts):
        return Decision(WORKERS_REASON)
    kind = worst(k for k in (run_kind(p) for p in parts) if k is not None)
    waits = not background and foreground_wait(text)
    heavy = kind is not None or bool(_LOCK.search(text) or _AUDIT.search(text))
    if heavy and state.active_s > BUDGET_MIN[role] * 60:
        report = _REPORT.get(role, "your report block")
        return Decision(BUDGET_REASON.format(role=role, minutes=BUDGET_MIN[role], report=report))
    if waits:
        return Decision(WAIT_REASON)
    if kind is None:
        return Decision(None)
    return _scope(role, kind, state)


def _text_blocks(content: object) -> list[str]:
    if not isinstance(content, list):
        return []
    return [
        str(b.get("text", "")) for b in content if isinstance(b, dict) and b.get("type") == "text"
    ]


def is_skill_load(record: Mapping[str, object]) -> bool:
    """A user record that is the orchestrator-mode skill text (not a tool result quoting it)."""
    if record.get("type") != "user":
        return False
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    texts = [content] if isinstance(content, str) else _text_blocks(content)
    return any(
        t.startswith(SKILL_MARKER) and ORCHESTRATOR_SKILL in t.split("\n", maxsplit=1)[0]
        for t in texts
    )


def last_assistant_text(lines: Iterable[str]) -> str:
    text = ""
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        message = record.get("message") if isinstance(record, dict) else None
        if record.get("type") != "assistant" or not isinstance(message, dict):
            continue
        found = _text_blocks(message.get("content"))
        if found:
            text = "\n".join(found)
    return text


def decide_stop(orchestrator: bool, stop_hook_active: bool, last_message: str) -> str | None:
    """Stop decision: a reason blocks the stop once; None allows it."""
    if not orchestrator or stop_hook_active:
        return None
    return None if RUN_STATE.search(last_message) else STOP_REASON


# --- I/O -------------------------------------------------------------------------------------


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name or "none")


def _state_path(session: str, name: str) -> Path:
    return Path(tempfile.gettempdir()) / STATE_DIR / _safe(session) / f"{_safe(name)}.json"


def _load(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save(path: Path, data: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    tmp.replace(path)


def _number(value: object, default: float = 0.0) -> float:
    return float(value) if isinstance(value, int | float) else default


def run_pre(payload: Mapping[str, object], now: float) -> dict[str, object] | None:
    role = payload.get("agent_type")
    tool_input = payload.get("tool_input")
    if payload.get("tool_name") != "Bash" or role not in ROLES or not isinstance(tool_input, dict):
        return None
    path = _state_path(str(payload.get("session_id", "")), str(payload.get("agent_id") or role))
    raw = _load(path)
    last = raw.get("last")
    state = AgentState(
        active_s=_number(raw.get("active_s")),
        last=_number(last) if isinstance(last, int | float) else None,
        e2e_runs=int(_number(raw.get("e2e_runs"))),
    )
    state = advance(state, now)
    decision = decide_pre(
        str(role),
        str(tool_input.get("command", "")),
        bool(tool_input.get("run_in_background")),
        state,
    )
    if decision.counts_e2e:
        state = replace(state, e2e_runs=state.e2e_runs + 1)
    _save(path, {"active_s": state.active_s, "last": state.last, "e2e_runs": state.e2e_runs})
    if decision.reason is None:
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": decision.reason,
        }
    }


def _scan_orchestrator(transcript: Path, session: str) -> bool:
    """Whether the session loaded the skill; scans only bytes added since the last call."""
    cache_path = _state_path(session, "_stop")
    cache = _load(cache_path)
    if cache.get("orchestrator") is True:
        return True
    offset = int(_number(cache.get("offset")))
    found = False
    with transcript.open("rb") as handle:
        if offset > transcript.stat().st_size:
            offset = 0
        handle.seek(offset)
        for raw in handle:
            if not raw.endswith(b"\n"):
                break  # a record still being written; read it next time
            offset += len(raw)
            if SKILL_MARKER.encode() in raw:
                try:
                    record = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(record, dict) and is_skill_load(record):
                    found = True
                    break
    _save(cache_path, {"orchestrator": found, "offset": offset})
    return found


def _tail_lines(transcript: Path) -> list[str]:
    with transcript.open("rb") as handle:
        size = transcript.stat().st_size
        handle.seek(max(size - TAIL_BYTES, 0))
        return handle.read().decode("utf-8", "replace").splitlines()


def run_stop(payload: Mapping[str, object]) -> str | None:
    if payload.get("agent_type"):
        return None
    transcript = Path(str(payload.get("transcript_path", "")))
    if not transcript.is_file():
        return None
    orchestrator = _scan_orchestrator(transcript, str(payload.get("session_id", "")))
    message = payload.get("last_assistant_message")
    if not isinstance(message, str) and orchestrator:
        message = last_assistant_text(_tail_lines(transcript))
    return decide_stop(orchestrator, bool(payload.get("stop_hook_active")), str(message or ""))


def main(argv: Sequence[str]) -> int:
    mode = argv[1] if len(argv) > 1 else ""
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if not isinstance(payload, dict):
            return 0
        if mode == "pre-tool":
            out = run_pre(payload, time.time())
            if out is not None:
                print(json.dumps(out))
        elif mode == "stop":
            reason = run_stop(payload)
            if reason is not None:
                print(reason, file=sys.stderr)
                return 2
    except Exception as exc:  # fail open: a broken guard must not block every agent
        if os.environ.get("AGENT_GUARD_DEBUG"):
            print(f"agent_guard error: {exc!r}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
