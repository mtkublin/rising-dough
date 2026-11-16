"""Mask secret-looking tokens in Terraform plan/apply output (T-D83, T-D85, ADR-0098).

Stdlib only. Usage:  terraform plan ... | python3 terraform/scripts/mask_plan.py

Belt and braces behind `sensitive()` on the compute module's `cloud_init`:
Terraform can print the PRIOR (state) value of an attribute unmasked, and
cloud-init embeds the age identity, Tailscale auth key, S3 keys and GHCR PAT.
Streams line by line so long plans are not buffered.

T-D85: also redacts the whole body of any heredoc opened by a `cloud-init` /
`cloud_init` / `user_data` / `user-data` key (random passwords and UUID-format
keys have no recognisable shape) and masks values of secret-named keys.
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

# `- "cloud-init" = <<-EOT`, `+ user_data = <<EOT`, `~ cloud_init = <<-EOT` ...
HEREDOC_OPEN = re.compile(
    r"""^\s*[-+~]?\s*["']?(?:cloud[-_]init|user[-_]data)["']?\s*=\s*<<-?(?P<delim>\w+)\s*$""",
    re.IGNORECASE,
)

# YAML (`KEY: "v"`), env (`KEY=v`) and HCL (`key = "v"`) lines with a secret-ish key.
SECRET_KEY_LINE = re.compile(
    r"""^(?P<head>\s*(?:[-+~]\s+)?["']?[\w.-]*?(?:PASSWORD|SECRET|TOKEN|AUTHKEY|IDENTITY|_KEY)"""
    r"""["']?\s*(?P<sep>[:=])\s*)(?=\S)""",
    re.IGNORECASE,
)

HEREDOC_INDENT_EXTRA = 4


def mask_secret_key_value(line: str) -> str:
    """Mask the value of a secret-named `KEY: v` / `KEY=v` line (keeps the key)."""
    match = SECRET_KEY_LINE.match(line)
    if match is None:
        return line
    value = '"***"' if match["sep"] == ":" else MASK
    newline = "\n" if line.endswith("\n") else ""
    return f"{match['head']}{value}{newline}"


def mask_line(line: str) -> str:
    """Return `line` with every known secret shape and secret-named value masked."""
    for pattern in PATTERNS:
        line = pattern.sub(MASK, line)
    return mask_secret_key_value(line)


def _redaction_line(indent: str, count: int) -> str:
    return f"{indent}(redacted by mask_plan.py: {count} lines)\n"


def mask_lines(lines: Iterable[str]) -> Iterator[str]:
    """Lazily mask an iterable of lines.

    Heredoc bodies opened by a cloud-init / user_data key are replaced by one
    placeholder line; the opening and closing delimiter lines are kept. An
    unterminated heredoc is redacted to end of input.
    """
    delimiter: str | None = None
    indent = ""
    hidden = 0
    for line in lines:
        if delimiter is None:
            yield mask_line(line)
            opened = HEREDOC_OPEN.match(line)
            if opened is not None:
                delimiter = opened["delim"]
                indent = " " * (len(line) - len(line.lstrip()) + HEREDOC_INDENT_EXTRA)
                hidden = 0
        elif line.strip() == delimiter:
            yield _redaction_line(indent, hidden)
            yield mask_line(line)
            delimiter = None
        else:
            hidden += 1
    if delimiter is not None:
        yield _redaction_line(indent, hidden)


def main() -> int:
    for out in mask_lines(sys.stdin):
        sys.stdout.write(out)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
