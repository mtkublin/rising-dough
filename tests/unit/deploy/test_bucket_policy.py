"""Bucket policy allow-list (T-D68, ADR-0091). Renders the provider-free
terraform module locally; no cloud calls."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

MODULE = Path(__file__).resolve().parents[3] / "terraform" / "modules" / "bucket_policy"
APP_ID = "11111111-1111-1111-1111-111111111111"
OPERATOR = "user_id:22222222-2222-2222-2222-222222222222"
RO_APP = "application_id:33333333-3333-3333-3333-333333333333"

pytestmark = pytest.mark.skipif(shutil.which("terraform") is None, reason="terraform not installed")


def _run(args: list[str], cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)  # noqa: S603
    assert result.returncode == 0, result.stderr
    return result.stdout


def _render(tmp_path: Path, admin: list[str], readonly: list[str]) -> dict[str, Any]:
    mod = tmp_path / "mod"
    shutil.copytree(MODULE, mod)
    root = tmp_path / "root"
    root.mkdir()
    (root / "main.tf").write_text(
        'module "p" {\n'
        f'  source = "{mod}"\n'
        '  bucket_name = "budget-planner-test-pl-waw"\n'
        f'  env_application_id = "{APP_ID}"\n'
        f"  admin_principals = {json.dumps(admin)}\n"
        f"  readonly_principals = {json.dumps(readonly)}\n"
        "}\n"
        'output "policy" { value = module.p.policy_json }\n'
    )
    _run(["terraform", "init", "-input=false", "-backend=false"], root)
    _run(["terraform", "apply", "-auto-approve", "-input=false"], root)
    out = _run(["terraform", "output", "-raw", "policy"], root)
    result: dict[str, Any] = json.loads(out)
    return result


def _statements(policy: dict[str, Any]) -> list[dict[str, Any]]:
    statements: list[dict[str, Any]] = policy["Statement"]
    return statements


def _principals(statement: dict[str, Any]) -> list[str]:
    principals: list[str] = statement["Principal"]["SCW"]
    return principals


def test_drill_policy_allows_only_env_application(tmp_path: Path) -> None:
    policy = _render(tmp_path, [], [])

    statements = _statements(policy)
    assert policy["Version"] == "2023-04-17"
    assert [s["Sid"] for s in statements] == ["AllowEnvApplication"]
    assert _principals(statements[0]) == [f"application_id:{APP_ID}"]


def test_policy_is_never_deny_only(tmp_path: Path) -> None:
    policy = _render(tmp_path, [OPERATOR], [RO_APP])

    effects = {s["Effect"] for s in _statements(policy)}
    assert effects == {"Allow"}


def test_env_application_cannot_list_delete_versions_or_manage_policy(tmp_path: Path) -> None:
    policy = _render(tmp_path, [], [])

    actions = set(_statements(policy)[0]["Action"])
    assert {"s3:PutObject", "s3:GetObject", "s3:ListBucket", "s3:DeleteObject"} <= actions
    assert "s3:*" not in actions
    assert not any("Policy" in a or "DeleteObjectVersion" in a for a in actions)


def test_prod_readonly_principals_get_read_only_actions(tmp_path: Path) -> None:
    policy = _render(tmp_path, [OPERATOR], [RO_APP])

    by_sid = {s["Sid"]: s for s in _statements(policy)}
    assert _principals(by_sid["AllowReadOnly"]) == [RO_APP]
    assert _principals(by_sid["AllowOperators"]) == [OPERATOR]
    ro_actions = set(by_sid["AllowReadOnly"]["Action"])
    assert "s3:GetObject" in ro_actions
    assert not {"s3:PutObject", "s3:DeleteObject"} & ro_actions
    assert RO_APP not in _principals(by_sid["AllowEnvApplication"])


def test_invalid_principal_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="admin principal"):
        _render(tmp_path, ["not-a-principal"], [])


# --- T-D69 / ADR-0092: stable restore-reader wiring (static; no cloud) ---

ROOT_TF = MODULE.parents[1] / "main.tf"
READER_MODULE = MODULE.parent / "restore_reader" / "main.tf"


def test_restore_reader_is_prod_only_and_merged_into_readonly_principals() -> None:
    main_tf = ROOT_TF.read_text()

    assert 'count  = var.env == "prod" ? 1 : 0' in main_tf
    assert 'module "restore_reader"' in main_tf
    assert "application_id:${m.application_id}" in main_tf
    assert "var.bucket_readonly_principals," in main_tf
    assert "readonly_principals = local.bucket_readonly_principals" in main_tf


def test_restore_reader_is_read_only_and_project_scoped() -> None:
    reader = READER_MODULE.read_text()

    assert '"ObjectStorageReadOnly"' in reader
    assert "FullAccess" not in reader
    assert "project_ids          = [var.scaleway_project_id]" in reader


def test_dns_records_use_zone_project() -> None:
    dns = (MODULE.parent / "dns" / "main.tf").read_text()

    assert dns.count("project_id = var.zone_project_id") == 2
