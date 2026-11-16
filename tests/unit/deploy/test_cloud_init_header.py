"""Static assertions on the cloud-init user-data header (T-D75, ADR-0035 §5). No network."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP = ROOT / "terraform" / "cloud-init" / "bootstrap.yaml.tpl"
CLOUD_CONFIG_HEADER = "#cloud-config"


def test_bootstrap_template_first_line_is_cloud_config() -> None:
    first_line = BOOTSTRAP.read_bytes().split(b"\n", 1)[0]

    assert first_line == CLOUD_CONFIG_HEADER.encode()
