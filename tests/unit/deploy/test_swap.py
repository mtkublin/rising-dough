"""Static assertions on the swapfile in the cloud-init template (T-D82, ADR-0032). No network."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BOOTSTRAP = (ROOT / "terraform" / "cloud-init" / "bootstrap.yaml.tpl").read_text()
ONE_GIB = 1073741824


def test_swap_key_declares_one_gib_swapfile() -> None:
    assert re.search(r"^swap:\n  filename: /swapfile\n", BOOTSTRAP, re.M)
    assert re.search(rf"^  size: {ONE_GIB}$", BOOTSTRAP, re.M)
    assert re.search(rf"^  maxsize: {ONE_GIB}$", BOOTSTRAP, re.M)


def test_swap_declared_before_packages_and_runcmd() -> None:
    swap = BOOTSTRAP.index("\nswap:")
    assert swap < BOOTSTRAP.index("\npackage_update:")
    assert swap < BOOTSTRAP.index("\nruncmd:")


def test_swappiness_persisted_and_applied_early() -> None:
    assert "/etc/sysctl.d/99-swappiness.conf" in BOOTSTRAP
    assert "vm.swappiness = 10" in BOOTSTRAP
    assert BOOTSTRAP.index("\nbootcmd:") < BOOTSTRAP.index("\npackage_update:")
    assert "vm.swappiness=10" in BOOTSTRAP


def test_cloud_config_header_still_first_line() -> None:
    assert BOOTSTRAP.startswith("#cloud-config\n")
