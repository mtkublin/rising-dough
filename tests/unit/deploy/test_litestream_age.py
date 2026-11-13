"""T-D56 / ADR-0078 §3: Litestream age replica encryption wiring.

Docker is not needed: these tests check the committed configs and templates so
the prod-sim stack, the prod cloud-init stack and the drill restore helper all
agree on one pinned Litestream tag and on age recipients/identities.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

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
        assert len(IMAGE_RE.findall(f.read_text())) == 2, f


def test_replicate_configs_encrypt_to_a_recipient_only() -> None:
    for path in (PRODSIM_REPLICATE, PROD_REPLICATE):
        age = _replica(path)["age"]
        assert "identities" not in age, path
        assert age["recipients"], path


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


def test_cloud_init_writes_identity_at_0600() -> None:
    text = (CLOUD_INIT / "bootstrap.yaml.tpl").read_text()
    m = re.search(r"path: /etc/budget-planner/litestream-age\.key\n\s+permissions: '(\d+)'", text)
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


def test_terraform_declares_sensitive_identity_without_default() -> None:
    text = (ROOT / "terraform" / "variables.tf").read_text()
    block = re.search(r'variable "litestream_age_identity" \{.*?\n\}', text, re.S)
    assert block is not None
    body = block.group(0)
    assert "sensitive   = true" in body
    assert "default" not in body
    assert 'variable "litestream_age_recipient"' in text
