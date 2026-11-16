"""Terraform required_version alignment (T-D79, ADR-0090). Static checks only; no cloud calls."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "terraform"
ROOT_VERSIONS = ROOT / "versions.tf"
REQUIRED_VERSION_RE = re.compile(r'required_version\s*=\s*"([^"]+)"')
MIN_TERRAFORM_FLOOR = "1.10.0"


def _required_version(path: Path) -> str:
    match = REQUIRED_VERSION_RE.search(path.read_text())
    assert match, f"required_version missing in {path}"
    return match.group(1)


def _versions_files() -> list[Path]:
    module_files = sorted((ROOT / "modules").glob("*/versions.tf"))
    return [*module_files, ROOT / "bootstrap" / "versions.tf"]


def test_root_floor_is_terraform_1_10() -> None:
    assert _required_version(ROOT_VERSIONS) == f">= {MIN_TERRAFORM_FLOOR}"


def test_every_module_required_version_matches_root() -> None:
    root_constraint = _required_version(ROOT_VERSIONS)
    files = _versions_files()
    assert files, "no module versions.tf files found"
    mismatched = {
        str(path.relative_to(ROOT)): _required_version(path)
        for path in files
        if _required_version(path) != root_constraint
    }
    assert not mismatched, f"required_version differs from root {root_constraint}: {mismatched}"
