"""base.html must work under the strict prod CSP (T-D140a, ADR-0113)."""

from __future__ import annotations

from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag
from fastapi.testclient import TestClient

_SELF_HOSTS = ("", "testserver")


def test_base_has_no_external_assets_or_inline_script(client: TestClient) -> None:
    r = client.get("/today")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "html.parser")
    # Scope: scripts owned by base.html (direct children of head/body). Inline
    # scripts inside page partials are covered by T-D140b / the e2e CSP guard.
    base_scripts = [
        s
        for s in soup.find_all("script")
        if s.parent is not None and s.parent.name in ("head", "body")
    ]
    assert base_scripts
    for script in base_scripts:
        src = str(script.get("src") or "")
        assert src, "inline <script> in base.html"
    for script in soup.find_all("script", src=True):
        assert urlparse(str(script["src"])).netloc in _SELF_HOSTS
    for link in soup.find_all("link", rel="stylesheet"):
        assert urlparse(str(link.get("href", ""))).netloc in _SELF_HOSTS
    for tag in (*soup.find_all("script", src=True), *soup.find_all("link", href=True)):
        url = str(tag.get("src") or tag.get("href"))
        assert "fonts.googleapis.com" not in url
        assert "unpkg.com" not in url


def test_base_declares_htmx_config_and_today_attribute(client: TestClient) -> None:
    soup = BeautifulSoup(client.get("/today").text, "html.parser")
    meta = soup.find("meta", attrs={"name": "htmx-config"})
    assert isinstance(meta, Tag)
    assert '"allowEval": false' in str(meta["content"])
    body = soup.body
    assert body is not None
    assert body.get("data-today-local")
