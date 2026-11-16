"""State bootstrap stack guards (T-D72, ADR-0096). Static checks only; no cloud calls."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3] / "terraform"
BOOTSTRAP = ROOT / "bootstrap"


def _bucket_block() -> str:
    text = (BOOTSTRAP / "main.tf").read_text()
    match = re.search(r'resource "scaleway_object_bucket" "tfstate" \{(.*?)\n\}\n', text, re.DOTALL)
    assert match, "tfstate bucket resource missing"
    return match.group(1)


def test_state_bucket_has_versioning_enabled() -> None:
    assert re.search(r"versioning \{\s*enabled\s*=\s*true", _bucket_block())


def test_state_bucket_is_protected_from_destroy() -> None:
    block = _bucket_block()
    assert re.search(r"prevent_destroy\s*=\s*true", block)
    assert re.search(r"force_destroy\s*=\s*false", block)


def test_state_bucket_is_private_and_has_no_policy() -> None:
    text = (BOOTSTRAP / "main.tf").read_text()
    assert re.search(r'acl\s*=\s*"private"', text)
    assert "scaleway_object_bucket_policy" not in text


def test_bootstrap_script_removed_and_state_not_ignored() -> None:
    assert not (ROOT / "scripts" / "bootstrap-state.sh").exists()
    assert "!bootstrap/terraform.tfstate" in (ROOT / ".gitignore").read_text()


def test_bootstrap_has_no_hardcoded_ids() -> None:
    text = "".join(p.read_text() for p in BOOTSTRAP.glob("*.tf"))
    assert not re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text)
