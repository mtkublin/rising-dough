# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G32: the closing gate (T-Q232; ADR-0130 closing amendment 2026-11-22).

Every allowlist under ``tests/architecture/allowlists/`` is empty of burn-down debt:

* no file except ``template_logic.toml`` has an ``[[entry]]`` row, and every ``[ceilings]`` value is 0;
* ``[[permanent]]`` and ``[[framework]]`` rows carry a non-empty ``reason`` and their path is named in ADR-0130
  (the closing amendment lists them), so a new one cannot land without an amendment;
* redesign carve-out: ``template_logic.toml`` holds at most ``CARVE_OUT_MAX`` (83 at the start, lowered by each surface task: the D3 entries of T-Q273) ``[[entry]]``
  rows, each with an ``owner`` that is a T-UR task heading in ``docs/plans/ui-redesign/tasks.md``; it has no other
  table. The redesign's last task (T-UR15) burns it to zero and then deletes the carve-out from this guard.

No allowlist file is exempt from the scan: a new file is checked the moment it exists.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from tests.architecture._ratchet import ALLOWLIST_DIR, REPO_ROOT

CARVE_OUT_FILE = "template_logic.toml"
CARVE_OUT_MAX = 59
ADR_FILE = (
    REPO_ROOT / "docs" / "adr" / "0130-prevention-regime-and-full-architectural-compliance.md"
)
UR_TASKS = REPO_ROOT / "docs" / "plans" / "ui-redesign" / "tasks.md"
OWNER = re.compile(r"^T-UR\d{2}$")
UR_HEADING = re.compile(r"^### \S+ (T-UR\d{2})\b", re.M)
ALLOWED_KEYS = frozenset({"guard", "entry", "permanent", "framework", "ceilings"})


def gate_problems(directory: Path, adr_text: str, ur_tasks: frozenset[str]) -> list[str]:
    """Return one message per closing-gate violation under ``directory``."""
    problems: list[str] = []
    for path in sorted(directory.glob("*.toml")):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        name = path.name
        problems += [
            f"{name}: unknown top-level key {k!r}" for k in sorted(set(data) - ALLOWED_KEYS)
        ]
        problems += [
            f"{name}: ceiling {k} = {v}, must be 0"
            for k, v in sorted(data.get("ceilings", {}).items())
            if v != 0
        ]
        problems += _entry_problems(name, data.get("entry", []), ur_tasks)
        for table in ("permanent", "framework"):
            for row in data.get(table, []):
                problems += _kept_row_problems(name, table, row, adr_text)
    return problems


def _entry_problems(
    name: str, rows: list[dict[str, object]], ur_tasks: frozenset[str]
) -> list[str]:
    if name != CARVE_OUT_FILE:
        return [
            f"{name}: [[entry]] burn-down row {r.get('path')} ({r.get('rule', '')}); fix the code and delete it"
            for r in rows
        ]
    problems = (
        [f"{name}: {len(rows)} entries, carve-out allows at most {CARVE_OUT_MAX}"]
        if len(rows) > CARVE_OUT_MAX
        else []
    )
    for r in rows:
        owner = str(r.get("owner", ""))
        if not OWNER.match(owner) or owner not in ur_tasks:
            problems.append(
                f"{name}: {r.get('path')} [{r.get('rule', '')}] has owner {owner!r}, need a T-UR task of docs/plans/ui-redesign/tasks.md"
            )
    return problems


def _kept_row_problems(name: str, table: str, row: dict[str, object], adr_text: str) -> list[str]:
    where = f"{name}: [[{table}]] {row.get('path')} [{row.get('rule', '')}]"
    if name == CARVE_OUT_FILE:
        return [f"{where}: the carve-out file takes [[entry]] rows only"]
    problems: list[str] = []
    if not str(row.get("reason", "")).strip():
        problems.append(f"{where}: no reason")
    if str(row.get("path", "")) not in adr_text:
        problems.append(f"{where}: path is not named in ADR-0130 (add it to the closing amendment)")
    return problems


def test_closing_gate_holds() -> None:
    ur = frozenset(UR_HEADING.findall(UR_TASKS.read_text(encoding="utf-8")))
    problems = gate_problems(ALLOWLIST_DIR, ADR_FILE.read_text(encoding="utf-8"), ur)
    assert not problems, (
        "\nG32 closing gate (ADR-0130 closing amendment 2026-11-22):\n"
        + "\n".join(f"  - {p}" for p in problems)
    )


def _write(directory: Path, name: str, body: str) -> None:
    (directory / name).write_text(f'guard = "{name}"\n{body}', encoding="utf-8")


def test_gate_flags_each_class_of_violation(tmp_path: Path) -> None:
    _write(tmp_path, "a.toml", '[[entry]]\npath = "src/x.py"\ncount = 1\nfinding = "Q-1"\n')
    _write(tmp_path, "b.toml", "[ceilings]\nPLC0415 = 1\n")
    _write(
        tmp_path,
        "c.toml",
        '[[permanent]]\npath = "src/p.py"\ncount = 1\nfinding = "f"\nreason = ""\n',
    )
    _write(
        tmp_path,
        "d.toml",
        '[[framework]]\npath = "src/f.py"\ncount = 1\nfinding = "f"\nreason = "why"\n',
    )
    _write(tmp_path, "e.toml", "[mystery]\nx = 1\n")
    _write(
        tmp_path,
        CARVE_OUT_FILE,
        '[[entry]]\npath = "t.html"\ncount = 1\nfinding = "Q-039"\n[[entry]]\npath = "u.html"\ncount = 1\nfinding = "Q-039"\nowner = "T-UR99"\n',
    )
    problems = gate_problems(tmp_path, "src/f.py", frozenset({"T-UR08"}))
    assert problems == [
        "a.toml: [[entry]] burn-down row src/x.py (); fix the code and delete it",
        "b.toml: ceiling PLC0415 = 1, must be 0",
        "c.toml: [[permanent]] src/p.py []: no reason",
        "c.toml: [[permanent]] src/p.py []: path is not named in ADR-0130 (add it to the closing amendment)",
        "e.toml: unknown top-level key 'mystery'",
        "template_logic.toml: t.html [] has owner '', need a T-UR task of docs/plans/ui-redesign/tasks.md",
        "template_logic.toml: u.html [] has owner 'T-UR99', need a T-UR task of docs/plans/ui-redesign/tasks.md",
    ]


def test_carve_out_maximum_is_pinned_and_the_file_fits_it() -> None:
    rows = tomllib.loads((ALLOWLIST_DIR / CARVE_OUT_FILE).read_text(encoding="utf-8")).get(
        "entry", []
    )
    assert CARVE_OUT_MAX == 59
    assert len(rows) <= CARVE_OUT_MAX


def test_gate_caps_the_carve_out_at_the_tagged_entry_maximum(tmp_path: Path) -> None:
    row = '[[entry]]\npath = "t{n}.html"\ncount = 1\nfinding = "Q-039"\nowner = "T-UR08"\n'
    _write(tmp_path, CARVE_OUT_FILE, "".join(row.format(n=n) for n in range(CARVE_OUT_MAX)))
    assert gate_problems(tmp_path, "", frozenset({"T-UR08"})) == []
    _write(tmp_path, CARVE_OUT_FILE, "".join(row.format(n=n) for n in range(CARVE_OUT_MAX + 1)))
    assert gate_problems(tmp_path, "", frozenset({"T-UR08"})) == [
        f"template_logic.toml: {CARVE_OUT_MAX + 1} entries, carve-out allows at most {CARVE_OUT_MAX}"
    ]
