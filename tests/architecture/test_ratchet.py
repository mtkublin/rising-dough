# Guard docstrings and teaching messages are prose; long lines are intentional.
"""The ratchet helper itself, and the hygiene of every allowlist file (ADR-0130 section 2)."""

from __future__ import annotations

from pathlib import Path

from tests.architecture._ratchet import (
    ALLOWLIST_DIR,
    Entry,
    Violation,
    dump_allowlist,
    load_entries,
    ratchet_problems,
)

ALLOWED = [Entry("src/a.py", "r", 2, "entry", "Q-001", "E01", "")]


def _violations(n: int) -> list[Violation]:
    return [Violation("src/a.py", i, "r") for i in range(1, n + 1)]


def test_equal_counts_pass() -> None:
    assert ratchet_problems("g", _violations(2), entries=ALLOWED) == []


def test_rising_count_fails_and_points_to_adr() -> None:
    (problem,) = ratchet_problems("g", _violations(3), entries=ALLOWED)
    assert "NEW violation" in problem and "ADR-0130" in problem


def test_falling_count_fails_and_names_the_file_to_edit() -> None:
    (problem,) = ratchet_problems("g", _violations(1), entries=ALLOWED)
    assert "allowlists/g.toml" in problem and "count = 1" in problem


def test_unlisted_path_has_zero_allowance() -> None:
    problems = ratchet_problems("g", [Violation("src/new.py", 4, "r")], entries=ALLOWED)
    assert any("src/new.py" in p and "NEW violation" in p for p in problems)


def test_dump_and_load_round_trip(tmp_path: Path) -> None:
    entries = [*ALLOWED, Entry("src/b.py", "", 1, "framework", "framework", "E04", "why")]
    (tmp_path / "g.toml").write_text(dump_allowlist("g", "header", entries))
    assert sorted(load_entries("g", tmp_path), key=lambda e: e.path) == entries


def test_every_allowlist_entry_is_documented_and_sorted() -> None:
    problems: list[str] = []
    for path in sorted(ALLOWLIST_DIR.glob("*.toml")):
        entries = load_entries(path.stem)
        for e in entries:
            if not e.finding:
                problems.append(f"{path.name}: {e.path} has no finding")
            if e.table != "entry" and not e.reason:
                problems.append(f"{path.name}: {e.table} entry {e.path} has no reason")
            if e.count < 1:
                problems.append(f"{path.name}: {e.path} has count {e.count}; delete the entry")
        keys = [(e.table, e.path, e.rule) for e in entries]
        if len(set(keys)) != len(keys):
            problems.append(f"{path.name}: duplicate (table, path, rule)")
    assert not problems, "\n".join(problems)
