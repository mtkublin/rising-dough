"""Static guards for the offline render check (T-D77). No terraform, no network."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "terraform.yml"
TFTEST = ROOT / "terraform" / "tests" / "render.tftest.hcl"
JUSTFILE = ROOT / "justfile"


def test_workflow_runs_render_check_with_required_schema() -> None:
    text = WORKFLOW.read_text()

    assert "tests/render/render_check.py --require-schema" in text
    assert "terraform test" in text


def test_tftest_asserts_cloud_config_header_with_mocked_provider() -> None:
    text = TFTEST.read_text()

    assert 'mock_provider "scaleway"' in text
    assert '"#cloud-config\\n"' in text


def test_justfile_has_tf_render_check_recipe() -> None:
    assert "\ntf-render-check:" in JUSTFILE.read_text()
