"""T-Q06 repro: query/form boundary inputs that surface as HTTP 500 (scratch DB only).

Run:
    cp /tmp/audit-C.sqlite /tmp/audit-C-in.sqlite
    BUDGET_DATABASE_URL=sqlite:////tmp/audit-C-in.sqlite PYTHONPATH=. \
      uv run python docs/plans/quality-audit/repro/C/repro_input_boundaries.py
"""

from __future__ import annotations

import os
import sys

URL = os.environ.get("BUDGET_DATABASE_URL", "")
if not URL.startswith("sqlite:////tmp/") or "budget.sqlite" in URL:
    sys.exit("refusing: BUDGET_DATABASE_URL must point at a /tmp scratch DB")

from fastapi.testclient import TestClient  # noqa: E402

from budget_planner.config import Settings  # noqa: E402
from budget_planner.web.app import create_app  # noqa: E402
from tests.auth_support import login_cookie  # noqa: E402

settings = Settings()
app = create_app(settings)
name, value = login_cookie(settings)
GETS = (
    "/budget?month=13",
    "/budget?month=0",
    "/budget?year=0",
    "/budget?year=10000",
    "/budget?month=abc",
    "/budget?year=2026&month=2",
    "/budget?year=2024&month=2",
    "/today/afford?amount=nan",
    "/today/afford?amount=inf",
    "/today/afford?amount=1e999",
    "/today/afford?amount=1.005",
    "/today/afford?amount=0.01",
    "/forecast?horizon=0",
    "/forecast?horizon=-5",
    "/forecast?horizon=100000",
    "/ledger?date_from=2026-02-30",
    "/ledger?page=0",
    "/ledger?page=-1",
    "/ledger?page_size=0",
    "/ledger?page_size=1000000",
)
with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as c:
    c.cookies.set(name, value)
    for url in GETS:
        r = c.get(url)
        print(f"{url:36} -> HTTP {r.status_code}")
    c.get("/accounts/1/reconcile")  # response sets the dev "csrf" cookie
    token = c.cookies.get("csrf", "")
    for raw in ("NaN", "Infinity", "1e999"):
        r = c.post(
            "/accounts/1/reconcile",
            data={"actual_balance": raw},
            headers={"X-CSRF-Token": token},
        )
        print(f"{'POST reconcile actual=' + raw:36} -> HTTP {r.status_code}")
