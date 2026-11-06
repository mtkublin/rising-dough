"""Root pytest conftest — environment pinning for the suite.

Pytest imports ``budget_planner.web.app`` through transitive imports in
most test modules. That module instantiates ``create_app()`` which in
turn calls ``get_settings()``. Under the default (``BUDGET_ENV=dev``)
the config emits a ``UserWarning`` about the dev cookie-secret fallback,
and the pytest ``filterwarnings = ["error"]`` policy turns that into a
collection-time error.

Pin ``BUDGET_ENV=test`` at import time so test runs stay quiet. Tests
that need to assert on dev / production behaviour override via
``monkeypatch`` in their own body.
"""

from __future__ import annotations

import os

os.environ.setdefault("BUDGET_ENV", "test")
