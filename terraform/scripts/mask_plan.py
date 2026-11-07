"""Mask secret-looking tokens in Terraform plan/apply output (T-D83, ADR-0098).

Stdlib only. Usage:  terraform plan ... | python3 terraform/scripts/mask_plan.py

Belt and braces behind `sensitive()` on the compute module's `cloud_init`:
Terraform can print the PRIOR (state) value of an attribute unmasked, and
cloud-init embeds the age identity, Tailscale auth key, S3 keys and GHCR PAT.
Streams line by line so long plans are not buffered.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable, Iterator

MASK = "***"

PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"AGE-SECRET-KEY-1[A-Z0-9]+"),
    re.compile(r"tskey-[a-z]+-[A-Za-z0-9-]+"),
    re.compile(r"ghp_[A-Za-z0-9]+"),
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"SCW[A-Z0-9]{17}"),
)


def mask_line(line: str) -> str:
    """Return `line` with every known secret shape replaced by `***`."""
    for pattern in PATTERNS:
        line = pattern.sub(MASK, line)
    return line


def mask_lines(lines: Iterable[str]) -> Iterator[str]:
    """Lazily mask an iterable of lines."""
    for line in lines:
        yield mask_line(line)


def main() -> int:
    for out in mask_lines(sys.stdin):
        sys.stdout.write(out)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
