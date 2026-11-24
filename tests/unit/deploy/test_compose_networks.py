"""T-Q306g: scripts/ci/compose_networks.py lists the template's ipam networks."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ci" / "compose_networks.py"
TEMPLATE = ROOT / "terraform" / "cloud-init" / "compose" / "docker-compose.yml.tpl"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("compose_networks", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_real_template_declares_edge_v2_with_its_subnet_and_gateway() -> None:
    rows = _module().ipam_networks(TEMPLATE.read_text())
    assert rows == [("budget-planner_edge_v2", "172.30.0.0/24", "172.30.0.1")]


def test_network_without_ipam_is_skipped_and_explicit_name_wins() -> None:
    text = """\
name: proj
networks:
  plain:
    driver: bridge
  a:
    ipam:
      config:
        - subnet: 10.0.0.0/24
          gateway: 10.0.0.1
  b:
    name: custom
    ipam:
      config:
        - subnet: 10.1.0.0/24
          gateway: 10.1.0.1
"""
    assert _module().ipam_networks(text) == [
        ("proj_a", "10.0.0.0/24", "10.0.0.1"),
        ("custom", "10.1.0.0/24", "10.1.0.1"),
    ]


def test_terraform_directive_lines_are_ignored() -> None:
    text = (
        "name: proj\n%{~ if x }\nnetworks:\n  n:\n    ipam:\n      config:\n"
        "        - subnet: 10.2.0.0/24\n          gateway: 10.2.0.1\n%{~ endif }\n"
    )
    assert _module().ipam_networks(text) == [("proj_n", "10.2.0.0/24", "10.2.0.1")]
