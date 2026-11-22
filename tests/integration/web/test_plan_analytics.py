"""Integration tests for GET /plan/analytics (T-R43, ADR-0056 §6).

Period parsing / fallback is a contract test (``tests/contract/test_plan_views.py``);
this file keeps the legacy tab alias.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.ui_map import _html, plan


def test_plan_tab_analytics_renders(client: TestClient) -> None:
    """Legacy /plan?tab=analytics still works and now carries a real bundle."""
    r = client.get("/plan?tab=analytics")
    assert r.status_code == 200
    assert _html.exists(r.text, plan.analytics_bundle)
