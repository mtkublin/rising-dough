"""T-D57 / ADR-0078 §4: the 37-day ceiling is consistent across Terraform,
Litestream config and the drill helper. No Docker or cloud access needed."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TF = ROOT / "terraform"
CEILING_DAYS = 37


def _read(rel: str) -> str:
    return (ROOT / rel).read_text()


def _block(text: str, name: str) -> str:
    match = re.search(rf'variable "{name}" \{{(.*?)\n\}}', text, re.S)
    assert match is not None, name
    return match.group(1)


def test_terraform_knob_defaults_to_37() -> None:
    block = _block((TF / "variables.tf").read_text(), "backup_max_age_days")
    assert re.search(r"default\s*=\s*37\b", block)


def test_lifecycle_days_derived_from_knob_and_retention() -> None:
    variables = (TF / "variables.tf").read_text()
    main = (TF / "main.tf").read_text()
    assert "var.backup_max_age_days - local.litestream_retention_days" in variables
    assert "local.lifecycle_days" in main
    assert not re.search(r"lifecycle_days\s*=\s*30\b", main)


def test_storage_module_default_is_seven_days() -> None:
    block = _block((TF / "modules" / "storage" / "variables.tf").read_text(), "lifecycle_days")
    assert re.search(r"default\s*=\s*7\b", block)


def test_litestream_retention_plus_lifecycle_equals_ceiling() -> None:
    tpl = _read("terraform/cloud-init/compose/litestream.yml.tpl")
    match = re.search(r"^\s*retention:\s*(\d+)h\s*$", tpl, re.M)
    assert match is not None
    retention_days = int(match.group(1)) // 24
    variables = (TF / "variables.tf").read_text()
    local = re.search(r"litestream_retention_days\s*=\s*(\d+)", variables)
    assert local is not None
    assert retention_days == int(local.group(1)) == 30
    lifecycle = CEILING_DAYS - retention_days
    assert lifecycle == 7


def test_drill_helper_deletes_copies_on_exit() -> None:
    script = _read("terraform/cloud-init/bin/restore-from-prod.tpl")
    assert "trap cleanup_copies EXIT" in script
    assert "rm -rf -- " in script
    assert "pre-migrate-" in script


def test_drill_workflow_asserts_no_extra_db_files() -> None:
    wf = _read(".github/workflows/restore-drill.yml")
    assert "Verify no extra DB copies remain" in wf
    assert wf.index("Verify no extra DB copies remain") < wf.index("Terraform destroy (drill)")


def test_terraform_knob_reaches_app_container_env() -> None:
    compose = _read("terraform/cloud-init/compose/docker-compose.yml.tpl")
    assert 'BUDGET_BACKUP_MAX_AGE_DAYS: "${backup_max_age_days}"' in compose
    user_data = _read("terraform/modules/compute/user_data.tf")
    assert "backup_max_age_days    = var.backup_max_age_days" in user_data
    assert "backup_max_age_days = var.backup_max_age_days" in _read("terraform/main.tf")
