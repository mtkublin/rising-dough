#!/usr/bin/env python3
"""Fail fast when a required root Terraform variable has no TF_VAR_* value (T-D70, ADR-0093).

A "required" variable is any ``variable`` block in ``terraform/variables.tf``
without a ``default``. In CI every such input arrives as ``TF_VAR_<name>`` from
a GitHub secret; a missing secret expands to an empty string, which would
otherwise surface as a confusing validation error or an interactive prompt.

Usage: python3 check_tf_vars.py [path/to/variables.tf]   (exit 1 on any gap)
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path

_DEFAULT_VARIABLES = Path(__file__).resolve().parent.parent / "variables.tf"
_HEADER = re.compile(r'^variable\s+"([^"]+)"\s*\{')
_DEFAULT = re.compile(r"^\s{2}default\s*=")


def required_variables(text: str) -> tuple[str, ...]:
    """Names of root variables declared without a ``default``."""
    required: list[str] = []
    current: str | None = None
    has_default = False
    for line in text.splitlines():
        header = _HEADER.match(line)
        if header:
            current, has_default = header.group(1), False
        elif current is not None and _DEFAULT.match(line):
            has_default = True
        elif current is not None and line.startswith("}"):
            if not has_default:
                required.append(current)
            current = None
    return tuple(required)


def missing_variables(names: tuple[str, ...], environ: Mapping[str, str]) -> tuple[str, ...]:
    """Required names whose ``TF_VAR_<name>`` is unset or blank."""
    return tuple(n for n in names if not environ.get(f"TF_VAR_{n}", "").strip())


def main(argv: list[str]) -> int:
    path = Path(argv[1]) if len(argv) > 1 else _DEFAULT_VARIABLES
    missing = missing_variables(required_variables(path.read_text()), os.environ)
    if not missing:
        print("All required TF_VAR_* inputs are set.")
        return 0
    print("::error::Missing required Terraform inputs (empty GitHub secret?):")
    for name in missing:
        print(f"::error::  TF_VAR_{name} is empty")
    print("See docs/plans/v3/operator-checklist.md A5 for the secret to add.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
