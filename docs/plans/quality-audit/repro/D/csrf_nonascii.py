"""D-02 sub-case: non-ASCII CSRF token makes secrets.compare_digest raise -> unauthenticated 500.

Run: uv run python docs/plans/quality-audit/repro/D/csrf_nonascii.py (scratch DB under /tmp only)
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

db = Path(tempfile.mkdtemp(prefix="auditDc-")) / "c.sqlite"
os.environ["BUDGET_DATABASE_URL"] = f"sqlite:///{db}"
subprocess.run([sys.executable, "-m", "budget_planner.db.startup_migrate"], check=True, capture_output=True)

from fastapi.testclient import TestClient  # noqa: E402

from budget_planner.config import Settings  # noqa: E402
from budget_planner.web.app import create_app  # noqa: E402

app = create_app(Settings(_env_file=None, database_url=f"sqlite:///{db}", env="test"))
with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as cl:
    cl.get("/auth/login")
    r = cl.post("/auth/login", data={"email": "a", "password": "b", "_csrf_token": "café"})
    print("form token non-ascii  ->", r.status_code)
