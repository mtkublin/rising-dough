"""T-D140c: the e2e CSP helper must keep finding the prod CSP in the Caddyfile."""

from __future__ import annotations

import pytest

from tests.e2e.csp import TEST_NONCE, parse_csp_template, prod_csp


def test_prod_csp_is_parsed_from_the_caddyfile() -> None:
    csp = prod_csp()
    assert "script-src 'self' 'nonce-" in csp
    assert f"'nonce-{TEST_NONCE}'" in csp
    assert "{vars.nonce}" not in csp


def test_parse_fails_loudly_when_the_header_is_missing() -> None:
    with pytest.raises(ValueError, match="exactly one CSP"):
        parse_csp_template("example.com {\n}\n")
