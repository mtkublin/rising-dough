"""T-D56 / ADR-0078 §3: Litestream age replica encryption wiring.

Docker is not needed: these tests check the committed configs and templates so
the prod-sim stack, the prod cloud-init stack and the drill restore helper all
agree on one pinned Litestream tag and on age recipients/identities.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]
DEV_KEY = ROOT / "deploy" / "litestream-age-DEV-ONLY.key"
PRODSIM_REPLICATE = ROOT / "deploy" / "litestream.yml"
PRODSIM_RESTORE = ROOT / "deploy" / "litestream-restore.yml"
CLOUD_INIT = ROOT / "terraform" / "cloud-init"
PROD_REPLICATE = CLOUD_INIT / "compose" / "litestream.yml.tpl"
PROD_RESTORE = CLOUD_INIT / "compose" / "litestream-restore.yml.tpl"
IMAGE_FILES = (
    ROOT / "docker-compose.yml",
    CLOUD_INIT / "compose" / "docker-compose.yml.tpl",
    CLOUD_INIT / "bin" / "restore-from-prod.tpl",
)
RECIPIENT_RE = re.compile(r"^age1[0-9a-z]{58}$")
IMAGE_RE = re.compile(r"litestream/litestream:([0-9][^\s'\"]*)")


def _replica(path: Path) -> dict[str, Any]:
    doc = yaml.safe_load(path.read_text())
    replica: dict[str, Any] = doc["dbs"][0]["replicas"][0]
    return replica


def test_one_exact_litestream_tag_everywhere() -> None:
    tags = {m for f in IMAGE_FILES for m in IMAGE_RE.findall(f.read_text())}
    assert len(tags) == 1, tags
    (tag,) = tags
    assert re.fullmatch(r"0\.3\.\d+", tag), f"age needs Litestream 0.3.x, got {tag}"


def test_every_litestream_service_uses_the_pin() -> None:
    for f in IMAGE_FILES[:2]:
        # Prod template also runs the T-D144 litestream-probe service.
        expected = 3 if f.name == "docker-compose.yml.tpl" else 2
        assert len(IMAGE_RE.findall(f.read_text())) == expected, f


def test_replicate_configs_carry_recipient_and_identity() -> None:
    # T-D136 / ADR-0114: calcPos decrypts the last WAL segment on every start,
    # so replicate needs the identity as well as the recipient.
    for path in (PRODSIM_REPLICATE, PROD_REPLICATE):
        age = _replica(path)["age"]
        assert age["recipients"], path
        assert len(age["identities"]) == 1, path
        assert "LITESTREAM_AGE_IDENTITY" in age["identities"][0], path


def test_litestream_services_use_the_entrypoint_and_mount_the_identity() -> None:
    for f, key_src in (
        (ROOT / "docker-compose.yml", "./deploy/litestream-age-DEV-ONLY.key"),
        (
            CLOUD_INIT / "compose" / "docker-compose.yml.tpl",
            "/etc/budget-planner/litestream-age.key",
        ),
    ):
        doc = yaml.safe_load(f.read_text().replace("%{~ if", "#").replace("%{~ endif }", "#"))
        svc = doc["services"]["litestream"]
        assert svc["entrypoint"] == ["/bin/sh", "/etc/litestream-entrypoint.sh"], f
        assert svc["command"][0] == "replicate", f
        mounts = svc["volumes"]
        assert any(m.endswith(":/etc/litestream-entrypoint.sh:ro") for m in mounts), f
        assert f"{key_src}:/run/litestream-age.key:ro" in mounts, f


def test_host_agent_delivers_entrypoint_and_restarts_litestream_on_changes() -> None:
    text = (CLOUD_INIT.parent / "modules" / "compute" / "user_data.tf").read_text()
    for name in (
        "litestream.yml",
        "litestream-entrypoint.sh",
        "litestream-age.key",
        "litestream.env",
    ):
        m = re.search(
            rf'path = "\$\{{local\.compose_dir\}}/{re.escape(name)}".*?restart = (\[[^\]]*\])', text
        )
        assert m is not None, name
        assert m.group(1) == '["litestream"]', name


def test_restore_configs_carry_an_identity() -> None:
    for path in (PRODSIM_RESTORE, PROD_RESTORE):
        identities = _replica(path)["age"]["identities"]
        assert len(identities) == 1
        assert "LITESTREAM_AGE_IDENTITY" in identities[0]


def test_restore_from_prod_template_uses_identity_file() -> None:
    text = (CLOUD_INIT / "bin" / "restore-from-prod.tpl").read_text()
    assert "identities:" in text
    assert "${age_key_file}" in text
    assert "lost" in text.lower()


def test_host_agent_writes_identity_at_0600() -> None:
    # ADR-0111: the host agent writes it from bp-config (compute module).
    text = (CLOUD_INIT.parent / "modules" / "compute" / "user_data.tf").read_text()
    m = re.search(r'path = "\$\{local\.compose_dir\}/litestream-age\.key", +mode = "(\d+)"', text)
    assert m is not None
    assert m.group(1) == "0600"


def test_dev_identity_matches_prodsim_recipient_and_is_labelled() -> None:
    lines = DEV_KEY.read_text().splitlines()
    assert "DEV-ONLY" in lines[0]
    assert any(ln.startswith("AGE-SECRET-KEY-1") for ln in lines)
    public = next(ln.split(": ", 1)[1] for ln in lines if ln.startswith("# public key: "))
    assert RECIPIENT_RE.match(public)
    assert _replica(PRODSIM_REPLICATE)["age"]["recipients"] == [public]


def test_dev_identity_is_allowlisted_in_secrets_baseline() -> None:
    baseline = (ROOT / ".secrets.baseline").read_text()
    assert r"deploy/litestream-age-DEV-ONLY\\.key" in baseline


def test_dev_identity_never_referenced_by_terraform() -> None:
    for path in (ROOT / "terraform").rglob("*"):
        if path.is_file() and path.suffix in {".tf", ".tpl", ".tfvars"}:
            assert "DEV-ONLY" not in path.read_text(), path


def test_terraform_age_inputs_are_prod_only_and_sensitive() -> None:
    """ADR-0135: prod supplies the pair, a drill generates its own, identities are sensitive."""
    text = (ROOT / "terraform" / "variables.tf").read_text()
    for name in ("litestream_age_identity", "restore_source_age_identity"):
        block = re.search(rf'variable "{name}" \{{.*?\n\}}', text, re.S)
        assert block is not None, name
        assert "sensitive   = true" in block.group(0), name
    prod = re.search(r'variable "litestream_age_identity" \{.*?\n\}', text, re.S)
    assert prod is not None
    assert 'var.env == "drill" || can(regex(' in prod.group(0)
    assert 'variable "litestream_age_recipient"' in text
    main = (ROOT / "terraform" / "main.tf").read_text()
    assert 'resource "age_secret_key" "drill"' in main
    assert 'count = var.env == "drill" ? 1 : 0' in main


def test_restore_helper_reads_the_prod_identity_not_the_host_key() -> None:
    """ADR-0135: restore-from-prod gets its own identity file, never litestream-age.key."""
    text = (ROOT / "terraform/modules/compute/user_data.tf").read_text()
    assert 'age_key_file     = "${local.compose_dir}/restore-source-age.key"' in text
    assert "var.restore_source_age_identity" in text
