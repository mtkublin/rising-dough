"""Static checks for T-D84 / ADR-0094: drill-only console password, docker group."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TF = ROOT / "terraform"
ROOT_VARS = (TF / "variables.tf").read_text()
ROOT_MAIN = (TF / "main.tf").read_text()
ROOT_OUT = (TF / "outputs.tf").read_text()
COMPUTE_VARS = (TF / "modules" / "compute" / "variables.tf").read_text()
USER_DATA = (TF / "modules" / "compute" / "user_data.tf").read_text()
BOOTSTRAP = (TF / "cloud-init" / "bootstrap.yaml.tpl").read_text()


def test_root_variable_defaults_false_and_is_drill_only() -> None:
    block = ROOT_VARS.split('variable "break_glass_console_password"')[1][:900]
    assert "default     = false" in block
    assert 'var.env == "drill"' in block
    assert "break_glass_console_password is drill-only" in block


def test_password_resource_is_conditional_and_typeable() -> None:
    block = ROOT_MAIN.split('resource "random_password" "console"')[1][:200]
    assert "count   = var.break_glass_console_password ? 1 : 0" in block
    assert "length  = 24" in block
    assert "special = false" in block


def test_only_bcrypt_hash_reaches_compute_and_template() -> None:
    assert "random_password.console[0].bcrypt_hash" in ROOT_MAIN
    assert "random_password.console[0].result" not in ROOT_MAIN
    assert "console_password_hash       = var.console_password_hash" in USER_DATA
    assert "console_password" not in USER_DATA.replace("console_password_hash", "")
    block = COMPUTE_VARS.split('variable "console_password_hash"')[1]
    assert "sensitive   = true" in block


def test_output_is_sensitive_and_null_when_disabled() -> None:
    block = ROOT_OUT.split('output "console_password"')[1][:500]
    assert "random_password.console[0].result : null" in block
    assert "sensitive   = true" in block


def test_template_unlocks_only_operator_with_hash_and_keeps_ssh_pwauth_off() -> None:
    assert "ssh_pwauth: false" in BOOTSTRAP
    assert BOOTSTRAP.count("hashed_passwd") == 1
    users = BOOTSTRAP[BOOTSTRAP.index("\nusers:") :]
    operator = users[users.index("- name: operator") : users.index("\nwrite_files:")]
    assert "hashed_passwd: '${console_password_hash}'" in operator
    assert 'console_password_hash != "" ? "false" : "true"' in operator
    assert "lock_passwd: true" in users.split("- name: deploy")[0]


def test_docker_group_declared_before_users() -> None:
    assert "\ngroups:\n  - docker\n" in BOOTSTRAP
    assert BOOTSTRAP.index("\ngroups:\n  - docker") < BOOTSTRAP.index("\nusers:")
