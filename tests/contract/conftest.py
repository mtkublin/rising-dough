"""Contract-test fixtures and the ``covers`` marker (ADR-0106 section 1).

``@covers("POST /transactions", "GET /transactions/new")`` declares which
routes a test exercises. ``tests/contract/test_route_coverage.py`` reads the
markers statically (AST), so no pytest plugin ordering is involved.
"""

from __future__ import annotations

import pytest

from budget_planner.services import _passwords
from tests.auth_support import FAST_ROUNDS
from tests.contract.route_inventory import KEY_PATTERN


def covers(*routes: str) -> pytest.MarkDecorator:
    """Marker factory: ``covers("<METHOD> <path template>", ...)``."""
    if not routes:
        raise ValueError("covers() needs at least one '<METHOD> <path>' key")
    for key in routes:
        if not KEY_PATTERN.match(key):
            raise ValueError(f"covers({key!r}): expected '<METHOD> <path>'")
    return pytest.mark.covers(*routes)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "covers(*routes): contract test covers these '<METHOD> <path>' routes (T-UT03)"
    )


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cheap bcrypt for tests under tests/contract only (conftest scope, not session-wide)."""
    monkeypatch.setattr(_passwords, "DEFAULT_ROUNDS", FAST_ROUNDS)
