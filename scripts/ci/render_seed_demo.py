"""Render `terraform/cloud-init/bin/seed-demo.tpl` without Terraform (T-Q306d, ADR-0149).

The gate's baseline host runs the baseline tag's Terraform, which does not install
`seed-demo`. The workflow therefore renders the PR head's template itself and pipes it
to the host over ssh. Only `${compose_dir}` and `${hostname}` are template variables;
`$${` is Terraform's escape for a literal `${`.

    python3 scripts/ci/render_seed_demo.py --hostname HOST [--compose-dir DIR] > seed-demo
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[2] / "terraform/cloud-init/bin/seed-demo.tpl"
# Same as terraform/modules/compute/user_data.tf `compose_dir`.
COMPOSE_DIR = "/etc/budget-planner"
VAR = re.compile(r"(?<!\$)\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
VALUE = re.compile(r"^[A-Za-z0-9._/-]+$")


class RenderError(ValueError):
    """Raised for an unknown template variable or an unsafe value."""


def render(template: str, values: Mapping[str, str]) -> str:
    """Substitute `${name}` from `values`, then unescape `$${`."""
    for value in values.values():
        if not VALUE.match(value):
            raise RenderError(f"unsafe template value: {value!r}")

    def sub(match: re.Match[str]) -> str:
        name = match.group(1)
        if name not in values:
            raise RenderError(f"unknown template variable: {name}")
        return values[name]

    return VAR.sub(sub, template).replace("$${", "${")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hostname", required=True)
    parser.add_argument("--compose-dir", default=COMPOSE_DIR)
    args = parser.parse_args(argv)
    try:
        out = render(
            TEMPLATE.read_text(),
            {"compose_dir": args.compose_dir, "hostname": args.hostname},
        )
    except RenderError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
