from fastapi.testclient import TestClient

import budget_planner
from budget_planner.config import Settings
from budget_planner.web.app import app, create_app


def test_package_importable() -> None:
    assert budget_planner.__name__ == "budget_planner"


def test_health_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_app_factory_accepts_settings() -> None:
    cfg = Settings(_env_file=None)
    created = create_app(settings=cfg)
    assert created.state.settings is cfg
