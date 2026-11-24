"""T-UR00b, ADR-0147 §1: handoff references are rendered in CI, never committed.

``tests/visual/reference/`` is a build output (gitignored); any tracked file there fails.
"""

from __future__ import annotations

import subprocess

from tests.architecture._ratchet import REPO_ROOT

REFERENCE_DIR = "tests/visual/reference"


def tracked_reference_files(listing: str) -> list[str]:
    return [line for line in listing.splitlines() if line.startswith(f"{REFERENCE_DIR}/")]


def test_listing_with_a_committed_png_is_flagged() -> None:
    assert tracked_reference_files(f"{REFERENCE_DIR}/today/x.1440.light.png\nREADME.md\n") == [
        f"{REFERENCE_DIR}/today/x.1440.light.png"
    ]


def test_no_reference_file_is_committed() -> None:
    out = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", "ls-files", REFERENCE_DIR],  # noqa: S607 - git on PATH, as in the hooks
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert tracked_reference_files(out) == [], (
        "references are rendered in CI (ADR-0147 §1); do not commit them"
    )
