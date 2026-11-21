"""T-D132 / ADR-0036: the CSP must be set from a response matcher, not a request matcher."""

from __future__ import annotations

import re
from pathlib import Path

CADDYFILE = Path(__file__).resolve().parents[3] / "terraform/cloud-init/compose/Caddyfile.tpl"


def _text() -> str:
    return CADDYFILE.read_text()


def _csp_lines(text: str) -> list[str]:
    return [
        ln
        for ln in text.splitlines()
        if ln.strip().startswith(("header ", "Content-Security-Policy"))
        and "Content-Security-Policy" in ln
    ]


def test_csp_is_set_exactly_once() -> None:
    assert len(_csp_lines(_text())) == 1


def test_csp_is_not_attached_via_site_level_request_matcher() -> None:
    # `header @name Content-Security-Policy ...` outside reverse_proxy tests the request.
    assert not re.search(r"^\s*header\s+@\w+\s+Content-Security-Policy", _text(), re.MULTILINE)


def test_csp_is_not_in_unsupported_match_block() -> None:
    assert not re.search(r"^\s*match\s*\{", _text(), re.MULTILINE)


def test_csp_lives_in_handle_response_with_html_response_matcher() -> None:
    text = _text()
    proxy = re.search(r"reverse_proxy 127.0.0.1:8000 \{(.*?)\n        \}\n", text, re.DOTALL)
    assert proxy is not None
    body = proxy.group(1)
    assert re.search(r"^\s*@html header Content-Type text/html\*\s*$", body, re.MULTILINE)
    block = re.search(r"handle_response @html \{(.*?)\n\s*\}", body, re.DOTALL)
    assert block is not None
    assert "Content-Security-Policy" in block.group(1)
    assert "copy_response" in block.group(1)


def test_csp_policy_uses_the_nonce_sent_upstream() -> None:
    text = _text()
    assert "header_up X-CSP-Nonce {vars.nonce}" in text
    (line,) = _csp_lines(text)
    assert "script-src 'self' 'nonce-{vars.nonce}'" in line
    # ADR-0113: a nonce in style-src would make browsers ignore 'unsafe-inline'.
    assert "style-src 'self' 'unsafe-inline';" in line
    assert "style-src 'self' 'nonce-" not in line
    assert "frame-ancestors 'none'" in line


def test_csp_script_src_stays_strict() -> None:
    (line,) = _csp_lines(_text())
    script_src = next(d for d in line.split(";") if "script-src" in d)
    assert "'unsafe-inline'" not in script_src
    assert "'unsafe-eval'" not in script_src
    assert "http" not in script_src
