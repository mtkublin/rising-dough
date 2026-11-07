"""Static assertions for T-D67 / ADR-0094: SSH only over Tailscale. No network."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
COMPUTE_MAIN = ROOT / "terraform" / "modules" / "compute" / "main.tf"
BOOTSTRAP = ROOT / "terraform" / "cloud-init" / "bootstrap.yaml.tpl"
ROOT_MAIN = ROOT / "terraform" / "main.tf"
WORKFLOWS = ROOT / ".github" / "workflows"
SSH_WORKFLOWS = ("deploy.yml", "rollback.yml", "restore-drill.yml")
TAILSCALE_ACTION = re.compile(r"uses:\s*tailscale/github-action@[0-9a-f]{40}\b")
SSH_CALL = re.compile(r"^\s*(?:result=\"\$\()?\s*ssh\s|\btimeout \d+ ssh\s", re.MULTILINE)


def _inbound_rules(tf: str) -> list[dict[str, str]]:
    rules: list[dict[str, str]] = []
    for block in re.findall(r"inbound_rule\s*\{(.*?)\n\s*\}", tf, flags=re.DOTALL):
        rules.append(dict(re.findall(r"(\w+)\s*=\s*\"?([\w.]+)\"?", block)))
    return rules


def test_security_group_has_no_port_22_rule() -> None:
    tf = COMPUTE_MAIN.read_text()

    # The only port-22 rule is the drill-only break-glass dynamic block (T-D81).
    assert len(re.findall(r"port\s*=\s*22\b", tf)) == 1
    assert "for_each = toset(var.break_glass_ssh_cidrs)" in tf
    assert all(rule.get("port") != "22" for rule in _inbound_rules(tf))


def test_security_group_keeps_web_ports_and_default_drop() -> None:
    tf = COMPUTE_MAIN.read_text()
    # ADR-0101: the web rules are a dynamic block (empty on the tailnet-only drill).
    rules = set(re.findall(r'\{ protocol = "(\w+)", port = (\d+) \}', tf))

    assert rules == {("TCP", "80"), ("TCP", "443"), ("UDP", "443")}
    assert 'inbound_default_policy  = "drop"' in tf


def test_cloud_init_joins_tailnet_with_tag_and_cleans_key() -> None:
    tpl = BOOTSTRAP.read_text()

    assert "pkgs.tailscale.com/stable/ubuntu/noble" in tpl
    assert "tailscale up" in tpl
    assert "--advertise-tags=${tailscale_tag}" in tpl
    assert "--hostname=${tailscale_hostname}" in tpl
    assert "--auth-key=file:/run/tailscale-authkey" in tpl
    assert "rm -f /run/tailscale-authkey" in tpl
    assert "--ssh" not in tpl  # no Tailscale SSH; normal sshd stays


def test_ufw_allows_ssh_only_on_tailscale_interface() -> None:
    tpl = BOOTSTRAP.read_text()

    rule = "ufw allow in on tailscale0 to any port 22 proto tcp"
    assert rule in tpl
    assert "ufw allow 22/tcp" not in tpl
    assert tpl.index(rule) < tpl.index("ufw --force enable")
    assert "ufw allow 80/tcp" in tpl
    assert "ufw allow 443/tcp" in tpl


def test_auth_key_is_single_use_tagged_and_drill_ephemeral() -> None:
    tf = ROOT_MAIN.read_text()
    block = re.search(r'resource "tailscale_tailnet_key" "vm" \{(.*?)\n\}', tf, flags=re.DOTALL)

    assert block is not None
    body = block.group(1)
    assert "reusable      = false" in body
    assert "preauthorized = true" in body
    assert 'ephemeral     = var.env == "drill"' in body
    assert "tags          = [local.tailscale_tag]" in body


@pytest.mark.parametrize("name", SSH_WORKFLOWS)
def test_workflow_joins_tailnet_before_first_ssh(name: str) -> None:
    text = (WORKFLOWS / name).read_text()
    action = TAILSCALE_ACTION.search(text)
    first_ssh = SSH_CALL.search(text)

    assert action is not None, "pinned tailscale/github-action step missing"
    assert first_ssh is not None
    assert action.start() < first_ssh.start()
    assert "tags: tag:ci" in text
    assert "secrets.TS_OAUTH_CLIENT_ID" in text
    assert "secrets.TS_OAUTH_SECRET" in text


def test_restore_drill_waits_for_tailnet_host_and_passes_oauth_vars() -> None:
    text = (WORKFLOWS / "restore-drill.yml").read_text()

    assert "DRILL_SSH_HOST: budget-planner-drill" in text
    assert "TF_VAR_tailscale_oauth_client_id" in text
    wait = text.index("Wait for drill host on the tailnet")
    assert wait < text.index("Trigger restore on drill host")
    assert 'operator@"${DRILL_HOST}"' not in text  # SSH never targets the public name
