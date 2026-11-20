# Guard docstrings and teaching messages are prose; long lines are intentional.
# ruff: noqa: E501
"""G16: CI and pre-commit parity (Q-044; ADR-0130 section 8).

Two assertions, both strict xfails until T-Q15b lands the matching change (then the XPASS fails the run and the marker
must be removed):

* ``ci.yml`` invokes ``pre-commit run --all-files`` with ``SKIP=pytest-fast`` (parity by construction);
* the tool versions pinned in ``.pre-commit-config.yaml`` (ruff, mypy, sqlfluff, djlint, bandit) equal ``uv.lock``.
"""

from __future__ import annotations

import re
import tomllib

import pytest
import yaml  # type: ignore[import-untyped,import-not-found,unused-ignore]

from tests.architecture._ratchet import REPO_ROOT

PINNED_TOOLS = {
    "ruff-pre-commit": "ruff",
    "mirrors-mypy": "mypy",
    "sqlfluff": "sqlfluff",
    "djLint": "djlint",
    "bandit": "bandit",
}


def ci_runs_precommit(ci_text: str) -> bool:
    """True when some step runs ``pre-commit run --all-files`` and the job skips only ``pytest-fast``."""
    workflow = yaml.safe_load(ci_text)
    for job in (workflow.get("jobs") or {}).values():
        for step in job.get("steps", []):
            command = str(step.get("run", ""))
            skipped = str((step.get("env") or {}).get("SKIP", ""))
            runs = re.search(r"pre-commit run\b.*--all-files", command)
            if runs and ("SKIP=pytest-fast" in command or skipped == "pytest-fast"):
                return True
    return False


def locked_versions(lock_text: str) -> dict[str, str]:
    return {p["name"]: p["version"] for p in tomllib.loads(lock_text)["package"]}


def pinned_versions(config_text: str) -> dict[str, str]:
    """Tool name -> version pinned in ``.pre-commit-config.yaml`` (``v`` prefix stripped)."""
    out: dict[str, str] = {}
    for repo in yaml.safe_load(config_text)["repos"]:
        key = repo["repo"].rstrip("/").rsplit("/", 1)[-1]
        if key in PINNED_TOOLS:
            out[PINNED_TOOLS[key]] = str(repo["rev"]).removeprefix("v")
    return out


def version_drift(pinned: dict[str, str], locked: dict[str, str]) -> dict[str, tuple[str, str]]:
    return {t: (v, locked.get(t, "?")) for t, v in pinned.items() if locked.get(t) != v}


@pytest.mark.xfail(
    strict=True,
    reason="T-Q15b adds the `pre-commit run --all-files` step (SKIP=pytest-fast) to ci.yml, ADR-0130 section 8",
)
def test_ci_runs_precommit_with_skip_pytest_fast() -> None:
    assert ci_runs_precommit(
        (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )


@pytest.mark.xfail(strict=True, reason="Q-044: T-Q15b aligns pre-commit tool versions with uv.lock")
def test_precommit_tool_versions_match_uv_lock() -> None:
    drift = version_drift(
        pinned_versions((REPO_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")),
        locked_versions((REPO_ROOT / "uv.lock").read_text(encoding="utf-8")),
    )
    assert not drift, f"pre-commit pins differ from uv.lock (pinned, locked): {drift} (Q-044)"


def test_parity_checks_detect_violations() -> None:
    ci = "jobs:\n  ci:\n    steps:\n      - run: pre-commit run --all-files\n        env:\n          SKIP: pytest-fast\n"
    assert ci_runs_precommit(ci)
    assert not ci_runs_precommit("jobs:\n  ci:\n    steps:\n      - run: just ci\n")
    assert version_drift({"ruff": "0.17.2"}, {"ruff": "0.18.0"}) == {"ruff": ("0.17.2", "0.18.0")}
    assert pinned_versions(
        "repos:\n  - repo: https://github.com/sqlfluff/sqlfluff\n    rev: 3.1.1\n"
    ) == {"sqlfluff": "3.1.1"}
