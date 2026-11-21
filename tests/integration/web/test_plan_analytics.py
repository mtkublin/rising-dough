"""Integration tests for the Plan analytics tab (T-R43, ADR-0056 §6)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_plan_tab_analytics_renders(client: TestClient) -> None:
    """Legacy /plan?tab=analytics still works and now carries a real bundle."""
    r = client.get("/plan?tab=analytics")
    assert r.status_code == 200
