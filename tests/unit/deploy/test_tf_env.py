"""T-D133: `scripts/ci/tf_env.py` is the one source of the TF_VAR_* mapping. No network."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("tf_env", ROOT / "scripts/ci/tf_env.py")
assert _spec is not None and _spec.loader is not None
tf_env = importlib.util.module_from_spec(_spec)
sys.modules["tf_env"] = tf_env
_spec.loader.exec_module(tf_env)

SECRETS = {
    "SCW_DEFAULT_PROJECT_ID": "proj",
    "OPERATOR_SSH_PUBKEY": "ssh-ed25519 AAAA op",
    "PROD_REPLICA_RO_ACCESS_KEY": "ro-id",
    "PROD_REPLICA_RO_SECRET_KEY": "ro-secret",  # pragma: allowlist secret
    "RESTORE_READER_APPLICATION_ID": "reader",
    "BUCKET_ADMIN_PRINCIPALS": '["a"]',
    "LITESTREAM_AGE_IDENTITY": "line1\nline2",
    "LITESTREAM_AGE_RECIPIENT": "age1recipient",
}
VARS = {"CI_SSH_PUBKEY": "ssh-ed25519 AAAA ci", "TAILNET_DNS_NAME": "tail1.ts.net"}


def _build(env: str, *, restore_source: bool = False) -> dict[str, str]:
    out: dict[str, str] = tf_env.build_env(
        env, SECRETS, VARS, owner="owner", run_id="99", restore_source=restore_source
    )
    return out


def test_drill_gets_drill_only_inputs() -> None:
    out = _build("drill")

    assert out["TF_VAR_env"] == "drill"
    assert out["TF_VAR_github_owner"] == "owner"
    assert out["TF_VAR_ci_ssh_pubkey"] == "ssh-ed25519 AAAA ci"  # T-D137
    assert out["TF_VAR_tailnet_dns_name"] == "tail1.ts.net"
    assert out["TF_VAR_drill_run_id"] == "99"  # T-D139
    assert out["TF_VAR_restore_reader_application_id"] == ""


def test_prod_replica_read_key_only_with_restore_source() -> None:
    """ADR-0132 / H4-03: an explore drill gets no prod read key; the restore drill apply does."""
    explore = _build("drill")
    restore = _build("drill", restore_source=True)

    assert explore["TF_VAR_scw_access_key_restore"] == ""
    assert explore["TF_VAR_scw_secret_key_restore"] == ""
    assert restore["TF_VAR_scw_access_key_restore"] == "ro-id"
    assert restore["TF_VAR_scw_secret_key_restore"] == SECRETS["PROD_REPLICA_RO_SECRET_KEY"]
    assert _build("prod", restore_source=True)["TF_VAR_scw_access_key_restore"] == ""


def test_drill_reads_no_age_secret_unless_restore_source() -> None:
    """ADR-0135: the drill generates its own key pair; no age value reaches an explore drill."""
    explore = _build("drill")
    restore = _build("drill", restore_source=True)

    for out in (explore, restore):
        assert out["TF_VAR_litestream_age_identity"] == ""
        assert out["TF_VAR_litestream_age_recipient"] == ""
    assert explore["TF_VAR_restore_source_age_identity"] == ""
    assert restore["TF_VAR_restore_source_age_identity"] == "line1\nline2"


def test_prod_keeps_its_own_age_pair_and_no_restore_source() -> None:
    out = _build("prod")
    restore_flag = _build("prod", restore_source=True)

    assert out["TF_VAR_litestream_age_identity"] == "line1\nline2"
    assert out["TF_VAR_litestream_age_recipient"] == "age1recipient"
    assert out["TF_VAR_restore_source_age_identity"] == ""
    assert restore_flag["TF_VAR_restore_source_age_identity"] == ""


def test_prod_never_gets_drill_only_inputs() -> None:
    out = _build("prod")

    assert out["TF_VAR_env"] == "prod"
    for name in (
        "ci_ssh_pubkey",
        "tailnet_dns_name",
        "drill_run_id",
        "scw_access_key_restore",
        "scw_secret_key_restore",
    ):
        assert out[f"TF_VAR_{name}"] == "", name
    assert out["TF_VAR_restore_reader_application_id"] == "reader"


def test_optional_inputs_fall_back_to_defaults() -> None:
    out = _build("prod")

    assert out["TF_VAR_managed_dns_zone"] == "false"
    assert out["TF_VAR_bucket_readonly_principals"] == "[]"
    assert out["TF_VAR_bucket_admin_principals"] == '["a"]'


def test_managed_dns_zone_is_read_from_variables_not_secrets() -> None:
    """T-D159: a secret `true` masks every `true` in CI logs and drops job outputs."""
    from_var = tf_env.build_env(
        "prod", SECRETS, {**VARS, "MANAGED_DNS_ZONE": "true"}, owner="o", run_id="1"
    )
    from_secret = tf_env.build_env(
        "prod", {**SECRETS, "MANAGED_DNS_ZONE": "true"}, VARS, owner="o", run_id="1"
    )

    assert from_var["TF_VAR_managed_dns_zone"] == "true"
    assert from_secret["TF_VAR_managed_dns_zone"] == "false"
    assert _build("drill")["TF_VAR_managed_dns_zone"] == "false"


def test_boolean_inputs_are_never_secrets() -> None:
    """T-D159 / ADR-0093 amendment: common tokens as secret values break CI output."""
    offenders = [
        e.name for e in tf_env.ENTRIES if e.default in ("true", "false") and e.source == "secret"
    ]

    assert offenders == []


def test_unknown_env_is_refused() -> None:
    with pytest.raises(tf_env.EnvError, match="drill or prod"):
        tf_env.build_env("staging", {}, {}, owner="o", run_id="1")


def test_github_env_uses_heredoc_for_multiline_values() -> None:
    text = tf_env.format_github_env({"TF_VAR_a": "x", "TF_VAR_b": "l1\nl2"})
    lines = text.splitlines()

    assert lines[0] == "TF_VAR_a=x"
    delimiter = lines[1].split("<<")[1]
    assert lines[2:5] == ["l1", "l2", delimiter]


def test_main_appends_to_github_env(tmp_path: Path) -> None:
    target = tmp_path / "env"
    environ = {
        "SECRETS_JSON": json.dumps(SECRETS),
        "VARS_JSON": json.dumps(VARS),
        "GITHUB_REPOSITORY_OWNER": "owner",
        "GITHUB_RUN_ID": "99",
        "GITHUB_ENV": str(target),
    }

    assert tf_env.main(["--env", "drill"], environ) == 0
    written = target.read_text()
    assert "TF_VAR_drill_run_id=99\n" in written
    assert "TF_VAR_litestream_age_identity=\n" in written  # drill: no age secret (ADR-0135)


def test_main_rejects_bad_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    environ = {"SECRETS_JSON": "[]", "GITHUB_ENV": str(tmp_path / "env")}

    assert tf_env.main(["--env", "prod"], environ) == 1
    assert "JSON object" in capsys.readouterr().err


def test_terraform_jobs_export_inputs_through_the_action_before_use() -> None:
    wf = yaml.safe_load((ROOT / ".github/workflows/terraform.yml").read_text())
    for job_id in ("plan", "apply"):
        steps = wf["jobs"][job_id]["steps"]
        names = [s.get("uses", "") for s in steps]
        action = names.index("./.github/actions/terraform-env")
        check = next(i for i, s in enumerate(steps) if "check_tf_vars.py" in s.get("run", ""))
        assert names.index("actions/checkout@" + names[0].split("@")[1]) < action < check
        assert steps[action]["with"]["secrets-json"] == "${{ toJSON(secrets) }}"
        assert not any(
            k.startswith("TF_VAR_") and k != "TF_VAR_app_image_ref"
            for k in wf["jobs"][job_id]["env"]
            # Workflow inputs, not secrets (T-D90; ADR-0127 §7 rehearsal knobs).
            if not k.endswith(("_expires_at", "_upload", "_root_volume_type", "_allow_empty_db"))
        )
