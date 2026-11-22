"""The visual suite's Playwright image is pinned and matches the locked package.

T-Q251, ADR-0027 amendment 2026-11-22; e2e.yml added by T-Q297. The workflows and the
justfile must name the same ``mcr.microsoft.com/playwright/python`` image, with an exact
version tag equal to the ``playwright`` version in ``uv.lock`` and a sha256 digest.
"""

from __future__ import annotations

import re
import tomllib

from tests.architecture._ratchet import REPO_ROOT

IMAGE = re.compile(
    r"mcr\.microsoft\.com/playwright/python:v(\d+\.\d+\.\d+)-[a-z]+@sha256:[0-9a-f]{64}"
)


def _images(relative: str) -> set[str]:
    return {m.group(0) for m in IMAGE.finditer((REPO_ROOT / relative).read_text())}


def _locked_playwright() -> str:
    lock = tomllib.loads((REPO_ROOT / "uv.lock").read_text())
    return str(next(p["version"] for p in lock["package"] if p["name"] == "playwright"))


WORKFLOWS = (".github/workflows/visual.yml", ".github/workflows/e2e.yml")


def test_workflows_and_justfile_use_one_pinned_image() -> None:
    justfile = _images("justfile")

    assert len(justfile) == 1
    for workflow in WORKFLOWS:
        assert _images(workflow) == justfile, workflow


def test_image_tag_matches_locked_playwright_version() -> None:
    for relative in (*WORKFLOWS, "justfile"):
        (image,) = _images(relative)

        assert IMAGE.match(image), relative
        assert f":v{_locked_playwright()}-" in image, relative
