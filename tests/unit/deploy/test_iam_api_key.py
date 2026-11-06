"""Static assertions on the Litestream IAM API key (T-D74, ADR-0092)."""

from __future__ import annotations

import re
from pathlib import Path

TF = Path(__file__).resolve().parents[3] / "terraform"


def _api_key_block() -> str:
    text = (TF / "modules" / "iam" / "main.tf").read_text()
    match = re.search(r'resource "scaleway_iam_api_key" "app" \{(.*?)\n\}', text, re.DOTALL)
    assert match, "scaleway_iam_api_key.app not found"
    return match.group(1)


def test_api_key_default_project_is_pinned() -> None:
    assert re.search(r"default_project_id\s*=\s*var\.scaleway_project_id", _api_key_block())


def test_api_key_ignores_provider_set_expiry() -> None:
    assert re.search(r"ignore_changes\s*=\s*\[expires_at\]", _api_key_block())


def test_expiry_exposed_as_non_sensitive_root_output() -> None:
    text = (TF / "outputs.tf").read_text()
    match = re.search(r'output "scw_app_key_expires_at" \{(.*?)\n\}', text, re.DOTALL)
    assert match
    assert "sensitive" not in match.group(1)
