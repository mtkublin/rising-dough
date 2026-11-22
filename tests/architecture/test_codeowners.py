"""CODEOWNERS covers the CI/CD trust boundary (T-Q239, Q-041; ADR-0099 amendment 2026-11-21)."""

from __future__ import annotations

from pathlib import Path

from tests.architecture._ratchet import REPO_ROOT

CODEOWNERS = REPO_ROOT / ".github" / "CODEOWNERS"
REQUIRED_PATHS = (
    "/.github/",
    "/scripts/ci/",
    "/terraform/",
    "/tests/architecture/ci_environments.toml",
    "/tests/architecture/allowlists/workflow_trust.toml",
)


def _rules(path: Path) -> dict[str, list[str]]:
    rules: dict[str, list[str]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pattern, *owners = line.split()
        rules[pattern] = owners
    return rules


def test_codeowners_file_exists() -> None:
    assert CODEOWNERS.is_file(), (
        "T-Q239: .github/CODEOWNERS is missing (ADR-0099 amendment 2026-11-21)"
    )


def test_codeowners_covers_trust_boundary_with_an_owner() -> None:
    rules = _rules(CODEOWNERS)
    missing = [p for p in REQUIRED_PATHS if p not in rules]
    assert not missing, f"CODEOWNERS lacks rules for: {missing}"
    bad = [
        p for p in REQUIRED_PATHS if not rules[p] or not all(o.startswith("@") for o in rules[p])
    ]
    assert not bad, f"CODEOWNERS rules need @owner entries: {bad}"


def test_codeowners_paths_exist() -> None:
    for pattern in REQUIRED_PATHS:
        assert (REPO_ROOT / pattern.lstrip("/")).exists(), f"CODEOWNERS path is stale: {pattern}"
