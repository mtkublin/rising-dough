"""Static assertions for T-D81 / ADR-0094: drill-only break-glass SSH. No network."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TF = ROOT / "terraform"
ROOT_VARS = (TF / "variables.tf").read_text()
ROOT_MAIN = (TF / "main.tf").read_text()
COMPUTE_MAIN = (TF / "modules" / "compute" / "main.tf").read_text()
USER_DATA = (TF / "modules" / "compute" / "user_data.tf").read_text()
BOOTSTRAP = (TF / "cloud-init" / "bootstrap.yaml.tpl").read_text()
RUNCMD = BOOTSTRAP[BOOTSTRAP.index("\nruncmd:") :]


def test_root_variable_defaults_empty_and_is_drill_only() -> None:
    assert 'variable "break_glass_ssh_cidrs"' in ROOT_VARS
    assert "default     = []" in ROOT_VARS.split('variable "break_glass_ssh_cidrs"')[1][:900]
    assert "can(cidrhost(c, 0))" in ROOT_VARS
    assert 'var.env == "drill"' in ROOT_VARS
    assert "break_glass_ssh_cidrs is drill-only" in ROOT_VARS


def test_root_passes_list_to_compute_and_template() -> None:
    assert "break_glass_ssh_cidrs = var.break_glass_ssh_cidrs" in ROOT_MAIN
    assert "break_glass_ssh_cidrs       = var.break_glass_ssh_cidrs" in USER_DATA


def test_security_group_port_22_only_via_dynamic_break_glass() -> None:
    assert 'dynamic "inbound_rule"' in COMPUTE_MAIN
    assert "var.break_glass_ssh_cidrs" in COMPUTE_MAIN
    assert COMPUTE_MAIN.count("port     = 22") == 1


def test_template_loops_cidrs_before_enable() -> None:
    loop = "%{ for cidr in break_glass_ssh_cidrs ~}"
    rule = "ufw allow from ${cidr} to any port 22 proto tcp"

    assert loop in BOOTSTRAP
    assert RUNCMD.index(loop) < RUNCMD.index(rule) < RUNCMD.index("ufw --force enable")
    assert BOOTSTRAP.startswith("#cloud-config\n")


def test_firewall_precedes_tailscale_install_and_join_has_timeout() -> None:
    assert RUNCMD.index("ufw --force enable") < RUNCMD.index("apt-get install -y tailscale")
    assert "timeout 120 tailscale up" in RUNCMD
