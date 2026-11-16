#!/usr/bin/env python3
"""T-D77: render the cloud-init user-data offline and lint it.

Plans the fixture in this directory (real compute module, dummy inputs, no
credentials, no API calls), extracts the rendered user-data from the plan and
checks: line 1 is exactly `#cloud-config`, the YAML parses, and (when the
binary exists) `cloud-init schema` passes. Usage:

    python3 terraform/tests/render/render_check.py [--out DIR] [--require-schema]
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
HEADER = "#cloud-config"
VARIANTS = {"restore-helper": True, "no-restore-helper": False}


def run(cmd: list[str], cwd: Path) -> str:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)  # noqa: S603 - fixed argv, no shell
    if result.returncode != 0:
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(f"command failed: {' '.join(cmd)}")
    return result.stdout


def render(plan_dir: Path, enable_restore_helper: bool) -> str:
    plan = plan_dir / "plan.bin"
    flag = f"enable_restore_helper={str(enable_restore_helper).lower()}"
    run(
        ["terraform", "plan", "-input=false", "-no-color", "-var", flag, f"-out={plan}"],
        HERE,
    )
    payload = json.loads(run(["terraform", "show", "-json", str(plan)], HERE))
    return str(payload["output_changes"]["user_data"]["after"])


def check_text(name: str, text: str) -> None:
    first_line = text.split("\n", 1)[0]
    if first_line != HEADER:
        raise SystemExit(f"[{name}] line 1 is {first_line!r}, expected {HEADER!r}")
    parsed = yaml.safe_load(text)
    if not isinstance(parsed, dict):
        raise SystemExit(f"[{name}] user-data is not a YAML mapping")
    print(f"[{name}] first line + YAML parse OK ({len(text.splitlines())} lines)")


def check_schema(name: str, path: Path, require: bool) -> None:
    binary = shutil.which("cloud-init")
    if binary is None:
        if require:
            raise SystemExit("cloud-init binary not found but --require-schema was set")
        print(f"[{name}] SKIPPED cloud-init schema: `cloud-init` not installed (CI runs it)")
        return
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [binary, "schema", "--config-file", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        sys.stderr.write(result.stderr)
        raise SystemExit(f"[{name}] cloud-init schema FAILED")
    print(f"[{name}] cloud-init schema OK")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, help="keep rendered files here (contains dummy secrets)"
    )
    parser.add_argument(
        "--require-schema", action="store_true", help="fail if cloud-init is missing"
    )
    args = parser.parse_args()

    run(["terraform", "init", "-backend=false", "-input=false"], HERE)
    with tempfile.TemporaryDirectory() as tmp:
        out = args.out or Path(tmp)
        out.mkdir(parents=True, exist_ok=True)
        for name, enable in VARIANTS.items():
            text = render(Path(tmp), enable)
            path = out / f"user-data.{name}.yaml"
            path.write_text(text)
            check_text(name, text)
            check_schema(name, path, args.require_schema)
    print("render check OK")


if __name__ == "__main__":
    main()
