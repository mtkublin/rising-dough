"""Static assertions for T-D97 / ADR-0101: the drill is tailnet-only. No network.

The rendered output is covered by `terraform test` (terraform/tests/render.tftest.hcl);
these tests pin the wiring of the Terraform sources and the workflows.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TF = ROOT / "terraform"
WORKFLOWS = ROOT / ".github" / "workflows"
TAILSCALE_ACTION = re.compile(r"uses:\s*tailscale/github-action@([0-9a-f]{40})\b")


def _text(path: Path) -> str:
    return path.read_text()


def _code(path: Path) -> str:
    return "\n".join(ln for ln in _text(path).splitlines() if not ln.lstrip().startswith("#"))


def test_dns_module_is_prod_only_and_state_is_moved() -> None:
    main = _text(TF / "main.tf")

    assert re.search(
        r'module "dns" \{[^}]*count\s*=\s*local\.tailnet_only \? 0 : 1', main, re.DOTALL
    )
    assert re.search(r"moved \{\s*from\s*=\s*module\.dns\s*to\s*=\s*module\.dns\[0\]\s*\}", main)


def test_drill_fqdn_is_magicdns_name_and_prod_keeps_domain() -> None:
    variables = _text(TF / "variables.tf")

    assert 'tailnet_only = var.env == "drill"' in variables
    assert '"${local.tailscale_hostname}.${var.tailnet_dns_name}"' in variables
    assert '"${local.subdomain}.${var.domain}"' in variables
    assert "tailnet_dns_name is required when env = 'drill'" in variables
    assert "must be empty on prod" in variables


def test_security_group_web_ports_only_when_public() -> None:
    compute = _text(TF / "modules" / "compute" / "main.tf")

    assert "public_web_rules = var.tailnet_only ? [] : [" in compute
    for port in ('"TCP", port = 80', '"TCP", port = 443', '"UDP", port = 443'):
        assert port in compute


def test_caddy_templates_prod_acme_and_drill_tailscaled_socket() -> None:
    caddy = _text(TF / "cloud-init" / "compose" / "Caddyfile.tpl")
    compose = _text(TF / "cloud-init" / "compose" / "docker-compose.yml.tpl")

    # ACME email and the port-80 site exist only for the public env.
    assert "%{~ if !tailnet_only }\n    email ops@${hostname}" in caddy
    assert "%{~ if !tailnet_only }\n\n# Port 80" in caddy
    # Security headers are not conditional.
    assert caddy.index("Strict-Transport-Security") > caddy.index("${hostname} {")
    assert "%{~ if tailnet_only }\n      # ADR-0101" in compose
    assert "- /var/run/tailscale:/var/run/tailscale" in compose
    assert '%{~ if !tailnet_only }\n      - "80:80"' in compose


def test_ci_drill_has_no_dns_permission_on_prod() -> None:
    ci = _text(TF / "bootstrap" / "ci" / "main.tf")
    start = ci.index('resource "scaleway_iam_policy" "ci_drill"')
    block = ci[start : ci.index('resource "scaleway_iam_api_key" "ci_drill"')]
    drill_policy = "\n".join(ln for ln in block.splitlines() if not ln.lstrip().startswith("#"))

    assert "DomainsDNSFullAccess" not in drill_policy
    assert "prod_project_id" not in drill_policy


def test_drill_smoke_joins_tailnet_and_probes_magicdns_name() -> None:
    wf = _text(WORKFLOWS / "drill.yml")
    pin = TAILSCALE_ACTION.search(wf)
    deploy_pin = TAILSCALE_ACTION.search(_text(WORKFLOWS / "deploy.yml"))

    assert pin is not None
    assert deploy_pin is not None
    assert pin.group(1) == deploy_pin.group(1)
    assert "tags: tag:ci" in wf
    assert "budget-planner-drill.${{ vars.TAILNET_DNS_NAME }}" in wf
    assert "vars.DRILL_URL" not in _code(WORKFLOWS / "drill.yml")


def test_terraform_workflow_passes_tailnet_dns_name_for_drill_only() -> None:
    wf = _text(WORKFLOWS / "terraform.yml")

    assert (
        "TF_VAR_tailnet_dns_name: ${{ matrix.env == 'drill' && vars.TAILNET_DNS_NAME || '' }}" in wf
    )
    assert (
        "TF_VAR_tailnet_dns_name: ${{ inputs.env == 'drill' && vars.TAILNET_DNS_NAME || '' }}" in wf
    )
