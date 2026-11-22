"""Real-IP chain is pinned, not trusted by wildcard (T-Q203, ADR-0133, ADR-0072 §4)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
DOCKERFILE = ROOT / "Dockerfile"
PROD_COMPOSE = ROOT / "terraform/cloud-init/compose/docker-compose.yml.tpl"
PRODSIM_COMPOSE = ROOT / "docker-compose.yml"
PROD_CADDY = ROOT / "terraform/cloud-init/compose/Caddyfile.tpl"
PRODSIM_CADDY = ROOT / "deploy/Caddyfile"
ALLOW_RE = re.compile(r'FORWARDED_ALLOW_IPS:\s*"([^"]+)"')


def test_dockerfile_never_trusts_forwarded_headers_from_everyone() -> None:
    text = DOCKERFILE.read_text()
    assert "--forwarded-allow-ips=*" not in text
    assert not re.search(r"FORWARDED_ALLOW_IPS=\*", text)
    assert re.search(r"FORWARDED_ALLOW_IPS=127\.0\.0\.1", text)


@pytest.mark.parametrize("path", [PROD_COMPOSE, PRODSIM_COMPOSE])
def test_compose_pins_forwarded_allow_ips_to_one_proxy_address(path: Path) -> None:
    match = ALLOW_RE.search(path.read_text())
    assert match is not None
    assert re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", match.group(1))


def test_prod_caddy_runs_on_host_network_and_app_binds_loopback_only() -> None:
    text = PROD_COMPOSE.read_text()
    assert 'network_mode: "host"' in text
    assert '"127.0.0.1:8000:8000"' in text


@pytest.mark.parametrize("path", [PROD_CADDY, PRODSIM_CADDY])
def test_caddy_overwrites_forwarded_for_and_real_ip(path: Path) -> None:
    text = path.read_text()
    assert "header_up X-Forwarded-For {remote_host}" in text
    assert "header_up X-Real-IP {remote_host}" in text
