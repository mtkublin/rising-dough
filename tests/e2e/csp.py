"""Prod CSP for e2e (T-D140c, ADR-0113).

The policy is parsed out of the Caddyfile template so the e2e guard cannot
drift from what prod sends. ``{vars.nonce}`` is replaced with a fixed test
nonce, which the harness also sends as ``X-CSP-Nonce``.
"""

from __future__ import annotations

import re
from pathlib import Path

CADDYFILE = Path(__file__).resolve().parents[2] / "terraform/cloud-init/compose/Caddyfile.tpl"
TEST_NONCE = "e2e-test-nonce-0000"
_NONCE_PLACEHOLDER = "{vars.nonce}"
_CSP_LINE = re.compile(r'^\s*header\s+Content-Security-Policy\s+"([^"]+)"\s*$', re.MULTILINE)


def parse_csp_template(caddyfile_text: str) -> str:
    """Return the raw CSP string (nonce placeholder intact) from a Caddyfile."""
    matches = _CSP_LINE.findall(caddyfile_text)
    if len(matches) != 1:
        raise ValueError(f"expected exactly one CSP header in the Caddyfile, found {len(matches)}")
    return str(matches[0])


def prod_csp(nonce: str = TEST_NONCE) -> str:
    """The prod CSP with ``nonce`` substituted."""
    return parse_csp_template(CADDYFILE.read_text()).replace(_NONCE_PLACEHOLDER, nonce)
