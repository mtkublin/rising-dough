# Guard docstrings, messages and divider comments are prose; long lines are intentional.
# ruff: noqa: E501
"""T-UR00: the old-frontend removal ledger (``docs/plans/ui-redesign/removal.md``) is honest (ADR-0107 §8).

* a row marked ``deleted`` must not exist on disk (a deleted file reappeared);
* a row marked ``delete`` or ``keep: ...`` must exist on disk (a typo or a deletion that forgot to flip the row);
* a ``keep`` reason must cite ADR-0107 §2 (only the kept-behaviour files may stay);
* a row path must have existed at the branch point (``bd3c1b0a``), when that commit is available (typo guard);
* a file under an old-frontend path that is not a ledger row fails: the old trees may only shrink. New files go
  under the new roots of ADR-0107 §3 and §4 (``ALLOWED_NEW_ROOTS``).
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from tests.architecture._ratchet import REPO_ROOT

LEDGER = REPO_ROOT / "docs" / "plans" / "ui-redesign" / "removal.md"
BRANCH_POINT = (
    "bd3c1b0a"  # `ui/sourdough` creation commit (T-UR00); the ledger is generated from its tree
)

WEB = "src/budget_planner/web"
# Old-frontend trees, scanned recursively; everything under them must be a ledger row unless it sits under an
# allowed new root. `tests/visual/baselines` is the name the ledger brief used; the old snapshots are `__snapshots__`.
OLD_ROOTS = (
    f"{WEB}/templates",
    f"{WEB}/static",
    "tests/visual/baselines",
    "tests/visual/__snapshots__",
)
# New roots the redesign adds (ADR-0107 §3: `static/rd/`, `layouts/`, `pages/`, `fragments/`). Files here are not
# old frontend and need no row.
ALLOWED_NEW_ROOTS = (
    f"{WEB}/templates/layouts",
    f"{WEB}/templates/pages",
    f"{WEB}/templates/fragments",
    f"{WEB}/static/rd",
)
IGNORED_PARTS = {"__pycache__", ".DS_Store"}
OWNER = re.compile(r"T-UR\d{2}[a-z]?")


@dataclass(frozen=True)
class Row:
    path: str
    owner: str
    status: str
    note: str


def parse_ledger(text: str) -> list[Row]:
    """Rows of every table whose header starts with ``| Path |`` (file tables); other tables are not read."""
    rows: list[Row] = []
    in_file_table = False
    for line in text.splitlines():
        if not line.startswith("|"):
            in_file_table = False
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0] == "Path":
            in_file_table = True
            continue
        if not in_file_table or set(cells[0]) <= {"-", ":", " "}:
            continue
        path = cells[0].strip("`")
        rows.append(Row(path, cells[1], cells[2], cells[3] if len(cells) > 3 else ""))
    return rows


def row_problems(rows: list[Row]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if row.path in seen:
            problems.append(f"{row.path}: listed twice")
        seen.add(row.path)
        if not OWNER.fullmatch(row.owner):
            problems.append(f"{row.path}: owner {row.owner!r} is not a T-URxx task id")
        if row.status in {"delete", "deleted"}:
            continue
        if not row.status.startswith("keep: "):
            problems.append(
                f"{row.path}: status {row.status!r} must be delete, deleted or keep: <reason>"
            )
        elif "ADR-0107 §2" not in row.status:
            problems.append(
                f"{row.path}: a keep reason must cite ADR-0107 §2 (only kept-behaviour files stay)"
            )
    return problems


def existence_problems(rows: list[Row], root: Path) -> list[str]:
    problems: list[str] = []
    for row in rows:
        exists = (root / row.path).is_file()
        if row.status == "deleted" and exists:
            problems.append(
                f"{row.path}: marked deleted but still exists (a deleted old-frontend file reappeared)"
            )
        elif row.status != "deleted" and not exists:
            problems.append(
                f"{row.path}: marked {row.status.split(':')[0]} but is not on disk "
                "(typo, or deleted without flipping the row to `deleted`)"
            )
    return problems


def unlisted_files(rows: list[Row], root: Path) -> list[str]:
    """Files under an old-frontend root that are neither a ledger row nor under an allowed new root."""
    listed = {row.path for row in rows}
    found: list[str] = []
    for old in OLD_ROOTS:
        base = root / old
        if not base.is_dir():
            continue
        for file in sorted(base.rglob("*")):
            rel = file.relative_to(root).as_posix()
            if not file.is_file() or IGNORED_PARTS & set(file.parts) or rel in listed:
                continue
            if any(rel.startswith(new + "/") for new in ALLOWED_NEW_ROOTS):
                continue
            found.append(
                f"{rel}: new file under an old-frontend path; the old trees may only shrink "
                f"(new files go under {', '.join(r.removeprefix(WEB + '/') for r in ALLOWED_NEW_ROOTS)})"
            )
    return found


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", *args],  # noqa: S607 - git on PATH, as in the hooks
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def branch_point_available(root: Path) -> bool:
    return _git(root, "cat-file", "-e", f"{BRANCH_POINT}^{{commit}}").returncode == 0


def never_existed(rows: list[Row], root: Path) -> list[str]:
    """Rows whose path is not in the branch-point tree (typo guard)."""
    done = _git(root, "ls-tree", "-r", "--name-only", BRANCH_POINT)
    tree = set(done.stdout.splitlines())
    return [
        f"{r.path}: not in the tree at {BRANCH_POINT}; the ledger lists only files that existed then"
        for r in rows
        if r.path not in tree
    ]


def ledger_problems(rows: list[Row], root: Path) -> list[str]:
    return [*row_problems(rows), *existence_problems(rows, root), *unlisted_files(rows, root)]


# ---------------------------------------------------------------------------------------------------------------
# The real ledger
# ---------------------------------------------------------------------------------------------------------------


def test_ledger_is_consistent_with_the_tree() -> None:
    rows = parse_ledger(LEDGER.read_text(encoding="utf-8"))
    assert rows, "removal.md has no file rows"
    problems = ledger_problems(rows, REPO_ROOT)
    assert not problems, "old-frontend removal ledger (ADR-0107 §8):\n" + "\n".join(problems)


def test_ledger_paths_existed_at_the_branch_point() -> None:
    if not branch_point_available(REPO_ROOT):
        return  # shallow clone without bd3c1b0a: the on-disk checks above still run
    rows = parse_ledger(LEDGER.read_text(encoding="utf-8"))
    problems = never_existed(rows, REPO_ROOT)
    assert not problems, "\n".join(problems)


# ---------------------------------------------------------------------------------------------------------------
# The guard bites (synthetic trees)
# ---------------------------------------------------------------------------------------------------------------


def _write(root: Path, rel: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x", encoding="utf-8")


def _tree(tmp_path: Path, files: list[str], ledger: str) -> tuple[list[Row], Path]:
    for rel in files:
        _write(tmp_path, rel)
    return parse_ledger(ledger), tmp_path


def _table(*rows: str) -> str:
    return "| Path | Owner | Status | Note |\n|---|---|---|---|\n" + "\n".join(rows) + "\n"


OLD = f"{WEB}/templates/partials/_nav.html"
LISTED = f"| `{OLD}` | T-UR15 | delete | |"


def test_parser_reads_only_file_tables() -> None:
    text = (
        _table(LISTED)
        + "\n| Item | Where | Owner | Status |\n|---|---|---|---|\n| `x` | `y` | T-UR15 | delete |\n"
    )
    assert parse_ledger(text) == [Row(OLD, "T-UR15", "delete", "")]


def test_clean_tree_has_no_problems(tmp_path: Path) -> None:
    rows, root = _tree(tmp_path, [OLD], _table(LISTED))
    assert ledger_problems(rows, root) == []


def test_deleted_row_that_exists_fails(tmp_path: Path) -> None:
    rows, root = _tree(tmp_path, [OLD], _table(f"| `{OLD}` | T-UR15 | deleted | |"))
    problems = ledger_problems(rows, root)
    assert len(problems) == 1
    assert "marked deleted but still exists" in problems[0]


def test_deleted_row_that_is_gone_passes(tmp_path: Path) -> None:
    rows, root = _tree(tmp_path, [], _table(f"| `{OLD}` | T-UR15 | deleted | |"))
    assert ledger_problems(rows, root) == []


def test_unlisted_new_file_in_old_directory_fails(tmp_path: Path) -> None:
    new = f"{WEB}/templates/partials/new.html"
    rows, root = _tree(tmp_path, [OLD, new], _table(LISTED))
    problems = ledger_problems(rows, root)
    assert len(problems) == 1
    assert problems[0].startswith(new)
    assert "only shrink" in problems[0]


def test_unlisted_file_in_unknown_new_subdirectory_fails(tmp_path: Path) -> None:
    stray = f"{WEB}/templates/other/page.html"
    rows, root = _tree(tmp_path, [OLD, stray], _table(LISTED))
    assert [p.split(":")[0] for p in ledger_problems(rows, root)] == [stray]


def test_new_files_under_allowed_roots_pass(tmp_path: Path) -> None:
    new_files = [
        f"{WEB}/templates/layouts/base.html",
        f"{WEB}/templates/pages/today/today.html",
        f"{WEB}/templates/fragments/rows/transaction-row.html",
        f"{WEB}/static/rd/css/main.css",
    ]
    rows, root = _tree(tmp_path, [OLD, *new_files], _table(LISTED))
    assert ledger_problems(rows, root) == []


def test_old_snapshot_directory_is_recursive(tmp_path: Path) -> None:
    new = "tests/visual/baselines/deep/today.png"
    rows, root = _tree(tmp_path, [OLD, new], _table(LISTED))
    assert [p.split(":")[0] for p in ledger_problems(rows, root)] == [new]


def test_row_for_a_missing_file_fails(tmp_path: Path) -> None:
    typo = f"{WEB}/templates/partials/_nvav.html"
    rows, root = _tree(tmp_path, [OLD], _table(LISTED, f"| `{typo}` | T-UR15 | delete | |"))
    problems = ledger_problems(rows, root)
    assert len(problems) == 1
    assert problems[0].startswith(typo)


def test_row_path_missing_from_branch_point_tree_fails() -> None:
    if not branch_point_available(REPO_ROOT):
        return
    rows = [
        Row(OLD, "T-UR15", "delete", ""),
        Row(f"{WEB}/templates/partials/_nvav.html", "T-UR15", "delete", ""),
    ]
    problems = never_existed(rows, REPO_ROOT)
    assert [p.split(":")[0] for p in problems] == [f"{WEB}/templates/partials/_nvav.html"]


def test_keep_needs_an_adr_0107_section_2_reason() -> None:
    ok = Row("a", "T-UR15", "keep: ADR-0107 §2: CSRF header", "")
    bad = Row("b", "T-UR15", "keep: looks useful", "")
    assert row_problems([ok]) == []
    assert "ADR-0107 §2" in row_problems([bad])[0]


def test_bad_status_and_owner_fail() -> None:
    problems = row_problems([Row("a", "someone", "maybe", "")])
    assert len(problems) == 2
