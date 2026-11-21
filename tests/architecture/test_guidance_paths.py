# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G15: guidance paths exist (Q-053; ADR-0130 section 10).

Every backticked repo path and every ``just <recipe>`` named in ``CLAUDE.md`` and ``.claude/skills/**/SKILL.md``
must exist, otherwise the guidance sends agents to files that are gone. Allowlist: ``allowlists/guidance_paths.toml``
(stale references that T-Q15c fixes when it edits ``CLAUDE.md`` / the skills; delete the entries then).
"""

from __future__ import annotations

import re
from pathlib import Path

from tests.architecture._ratchet import REPO_ROOT, Violation, assert_ratchet

GUARD = "guidance_paths"
HEADER = "G15 guidance_paths: stale paths and just recipes in CLAUDE.md and skills (Q-053). T-Q15c removes these."
TICKS = re.compile(r"`([^`\n]+)`")
PATH_PREFIXES = (
    "docs/",
    "src/",
    "tests/",
    "scripts/",
    "terraform/",
    ".github/",
    ".claude/",
    "migrations/",
    "data/",
)
JUST_CMD = re.compile(r"^just\s+([a-z][a-z0-9-]*)")
RECIPE = re.compile(r"^([a-z][a-z0-9-]*)\b[^:\n]*:(?!=)", re.M)
IGNORED_PATH_PARTS = (
    "<",
    ">",
    "*",
    "{",
    "$",
    "...",
    "budget.sqlite",
    "demo.sqlite",
    "terraform/.env",
)
TEACH = (
    "G15 guidance paths: the path or `just` recipe named in CLAUDE.md or a skill does not exist. Fix the guidance "
    "(docs/plans/<plan>/tasks.md, justfile recipe names) so agents are not sent to nothing (Q-053)."
)


def guidance_files(root: Path) -> list[Path]:
    return [root / "CLAUDE.md", *sorted((root / ".claude" / "skills").glob("**/SKILL.md"))]


def just_recipes(justfile_text: str) -> set[str]:
    return set(RECIPE.findall(justfile_text))


def scan_text(rel: str, text: str, root: Path, recipes: set[str]) -> list[Violation]:
    found: list[Violation] = []
    for number, line in enumerate(text.splitlines(), 1):
        for token in TICKS.findall(line):
            token_text = token.strip()
            cmd = JUST_CMD.match(token_text)
            if cmd:
                if cmd.group(1) not in recipes:
                    found.append(Violation(rel, number, "missing-recipe", token_text))
                continue
            first = token_text.split()[0] if token_text.split() else ""
            if first.startswith(PATH_PREFIXES) and not any(
                part in first for part in IGNORED_PATH_PARTS
            ):
                target = first.split("#")[0].rstrip(".,;:)")
                if target and not (root / target).exists():
                    found.append(Violation(rel, number, "missing-path", target))
    return found


def collect() -> list[Violation]:
    recipes = just_recipes((REPO_ROOT / "justfile").read_text(encoding="utf-8"))
    found: list[Violation] = []
    for path in guidance_files(REPO_ROOT):
        rel = path.relative_to(REPO_ROOT).as_posix()
        found += scan_text(rel, path.read_text(encoding="utf-8"), REPO_ROOT, recipes)
    return found


def meta(_v: Violation) -> tuple[str, str, str, str]:
    return "entry", "Q-053", "E14", ""


def test_guidance_paths_match_allowlist() -> None:
    assert_ratchet(GUARD, collect(), TEACH)


def test_guidance_paths_detect_dead_path_and_recipe(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "real.md").write_text("x")
    text = "see `docs/real.md`, `docs/gone.md` and run `just nothing` or `just test`\n"
    found = scan_text("CLAUDE.md", text, tmp_path, {"test"})
    assert [(v.rule, v.detail) for v in found] == [
        ("missing-path", "docs/gone.md"),
        ("missing-recipe", "just nothing"),
    ]
