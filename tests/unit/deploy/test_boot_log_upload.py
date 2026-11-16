"""Static checks for T-D86 / ADR-0094: drill-only boot log upload from bootcmd."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TF = ROOT / "terraform"
ROOT_VARS = (TF / "variables.tf").read_text()
ROOT_MAIN = (TF / "main.tf").read_text()
USER_DATA = (TF / "modules" / "compute" / "user_data.tf").read_text()
STORAGE = (TF / "modules" / "storage" / "main.tf").read_text()
BOOTSTRAP = (TF / "cloud-init" / "bootstrap.yaml.tpl").read_text()
BLOCK = BOOTSTRAP.split("%{ if boot_log_upload }")[1].split("%{ endif }")[0]


def test_root_variable_defaults_false_and_is_drill_only() -> None:
    block = ROOT_VARS.split('variable "boot_log_upload"')[1][:700]
    assert "default     = false" in block
    assert 'var.env == "drill"' in block
    assert "boot_log_upload is drill-only" in block


def test_variable_is_passed_to_compute_and_template() -> None:
    assert "boot_log_upload = var.boot_log_upload" in ROOT_MAIN
    assert "boot_log_upload             = var.boot_log_upload" in USER_DATA


def test_lifecycle_rule_is_drill_gated() -> None:
    assert 'expire_boot_logs = var.env == "drill"' in ROOT_MAIN
    assert "for_each = var.expire_boot_logs ? [1] : []" in STORAGE
    assert 'prefix  = "boot-logs/"' in STORAGE
    assert "days = 7" in STORAGE


def test_uploader_is_written_by_bootcmd_and_detached() -> None:
    assert BOOTSTRAP.index("bootcmd:") < BOOTSTRAP.index("%{ if boot_log_upload }")
    assert BOOTSTRAP.index("%{ endif }") < BOOTSTRAP.index("\npackage_update")
    assert "\n  - |\n" in BLOCK
    assert "umask 077" in BLOCK
    assert "/run/boot-log-upload.env" in BLOCK
    assert "nohup setsid sh /run/boot-log-upload.sh" in BLOCK
    assert ") || true" in BLOCK
    assert "set -e" not in BLOCK


def test_uploader_covers_files_schedule_and_sigv4() -> None:
    for name in (
        "cloud-init.log",
        "cloud-init-output.log",
        "journalctl -b --no-pager",
        "dmesg",
        "cloud-init status --long",
        "ps auxf",
        "free -m",
    ):
        assert name in BLOCK
    assert '--aws-sigv4 "aws:amz:$REGION:s3"' in BLOCK
    assert "boot-logs/$IID/$BID/$1" in BLOCK
    assert "/proc/sys/kernel/random/boot_id" in BLOCK
    assert "169.254.42.42/conf?format=json" in BLOCK
    assert "-lt 120 ]; do snap; sleep 30;" in BLOCK
    assert "-lt 24 ]; do snap; sleep 300;" in BLOCK


def test_uploader_redacts_secrets() -> None:
    assert "tskey-[A-Za-z0-9-]+" in BLOCK
    assert "AGE-SECRET-KEY-1[A-Z0-9]+" in BLOCK
    assert "PASSWORD|SECRET|TOKEN|_KEY" in BLOCK


def test_no_boot_log_text_outside_conditional() -> None:
    outside = BOOTSTRAP.replace(BLOCK, "")
    assert "boot-log" not in outside.replace("%{ if boot_log_upload }", "")
