"""Print the compose networks that declare ipam, as `name subnet gateway` lines (T-Q306g).

`name` is the Docker network name on the host: `<project>_<key>` (the template's
top-level `name:` is the project), or the network's own `name:` when it sets one.
The drill gate compares these lines with `docker network inspect` on the host.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import yaml


def _ipam_entry(spec: dict[str, Any]) -> tuple[str, str] | None:
    configs = (spec.get("ipam") or {}).get("config") or []
    if not configs:
        return None
    first = configs[0]
    return str(first.get("subnet", "")), str(first.get("gateway", ""))


ARGV_LEN = 2


def ipam_networks(template: str) -> list[tuple[str, str, str]]:
    """Return (docker network name, subnet, gateway) for every network with ipam."""
    # Terraform directive lines (`%{ if ... }`) are not YAML; both branches stay.
    plain = "\n".join(ln for ln in template.splitlines() if not ln.lstrip().startswith("%{"))
    doc = yaml.safe_load(plain) or {}
    project = str(doc.get("name", ""))
    rows: list[tuple[str, str, str]] = []
    for key, spec in sorted((doc.get("networks") or {}).items()):
        entry = _ipam_entry(spec or {})
        if entry is None:
            continue
        name = str((spec or {}).get("name") or f"{project}_{key}")
        rows.append((name, entry[0], entry[1]))
    return rows


def main(argv: list[str]) -> int:
    if len(argv) != ARGV_LEN:
        print("usage: compose_networks.py <docker-compose.yml.tpl>", file=sys.stderr)
        return 2
    for name, subnet, gateway in ipam_networks(Path(argv[1]).read_text()):
        print(name, subnet, gateway)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
