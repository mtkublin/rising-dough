"""T-Q07 Track D probes: headers on every response class, CSRF, input validation (422 vs 500),
session lifecycle. Scratch DB only. Run: uv run python docs/plans/quality-audit/repro/D/probe_headers_validation.py
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

WORK = Path(tempfile.mkdtemp(prefix="auditDp-"))
DB = WORK / "p.sqlite"
os.environ["BUDGET_DATABASE_URL"] = f"sqlite:///{DB}"

from fastapi.testclient import TestClient  # noqa: E402

from budget_planner.config import Settings  # noqa: E402
from budget_planner.repositories import sessions as sessions_repo  # noqa: E402
from budget_planner.services import _passwords  # noqa: E402
from budget_planner.web.app import create_app  # noqa: E402

_passwords.DEFAULT_ROUNDS = 4
subprocess.run([sys.executable, "-m", "budget_planner.db.startup_migrate"], check=True, capture_output=True)
c = sqlite3.connect(DB)
pw = _passwords.hash_password("correct-horse-battery", rounds=4)
c.execute("UPDATE users SET email='u@x.test', password_hash=? WHERE id=1", (pw,))
c.execute("INSERT INTO accounts(user_id,name,currency) VALUES (1,'a','PLN')")
c.execute("INSERT INTO categories(user_id,name,direction) VALUES (1,'e','expense')")
c.commit()
c.close()
settings = Settings(_env_file=None, database_url=f"sqlite:///{DB}", env="test")
app = create_app(settings)
cn = sqlite3.connect(DB)
cn.row_factory = sqlite3.Row
TOK = sessions_repo.create_session(cn, 1, ip="127.0.0.1", user_agent="p").token
cn.close()
SEC = ["strict-transport-security", "x-frame-options", "x-content-type-options", "referrer-policy",
       "permissions-policy", "content-security-policy", "cache-control", "x-request-id"]


def show(tag: str, r) -> None:
    h = {k: r.headers.get(k) for k in SEC}
    missing = [k for k, v in h.items() if v is None]
    print(f"{tag:55s} {r.status_code}  cache-control={h['cache-control']!r}  missing={missing}")


with TestClient(app, base_url="https://testserver", follow_redirects=False, raise_server_exceptions=False) as cl:
    cl.get("/healthz")
    csrf = cl.cookies.get("__Host-csrf")
    print("== anonymous")
    show("GET /auth/login", cl.get("/auth/login"))
    show("GET /today (redirect)", cl.get("/today"))
    show("GET /health", cl.get("/health"))
    show("GET /nope (404 anon)", cl.get("/nope"))
    show("POST /auth/login no csrf", cl.post("/auth/login", data={"email": "a", "password": "b"}))
    show("POST /auth/login bad creds", cl.post("/auth/login", data={"email": "a", "password": "b"}, headers={"X-CSRF-Token": csrf}))
    show("GET /static/app.css", cl.get("/static/app.css"))
    show("GET /openapi.json anon", cl.get("/openapi.json"))
    print("== authenticated")
    cl.cookies.set("__Host-session", TOK)
    H = {"X-CSRF-Token": csrf}
    show("GET /today", cl.get("/today"))
    show("GET /nope (404 auth)", cl.get("/nope"))
    show("GET /docs", cl.get("/docs"))
    show("GET /openapi.json", cl.get("/openapi.json"))
    show("POST /transactions no csrf", cl.post("/transactions", data={}))
    show("POST /transactions empty form (422)", cl.post("/transactions", data={}, headers=H))
    show("GET /transactions/abc/edit (422 path)", cl.get("/transactions/abc/edit"))
    show("GET /transactions/99999999999999999999/edit", cl.get("/transactions/99999999999999999999/edit"))
    show("GET /transactions/-1/edit", cl.get("/transactions/-1/edit"))
    base = {"operation_date": "2026-11-12", "category_id": "3", "account_id": "1", "amount": "1.00"}
    for label, over in {
        "amount=NaN": {"amount": "NaN"},
        "amount=Infinity": {"amount": "Infinity"},
        "amount=1e400": {"amount": "1e400"},
        "amount=9999999999999999999999": {"amount": "9999999999999999999999"},
        "amount=-1": {"amount": "-1"},
        "date=0000-00-00": {"operation_date": "0000-00-00"},
        "date=9999-12-31": {"operation_date": "9999-12-31"},
        "category_id=99999999999999999999": {"category_id": "99999999999999999999"},
        "description=100k chars": {"description": "x" * 100_000},
        "description=NUL": {"description": "a\x00b"},
    }.items():
        show(f"POST /transactions {label}", cl.post("/transactions", data={**base, **over}, headers=H))
    show("GET /ledger?page=-5", cl.get("/ledger?page=-5"))
    show("GET /ledger?page=999999999999999999999", cl.get("/ledger?page=999999999999999999999"))
    show("GET /ledger?page_size=999999999", cl.get("/ledger?page_size=999999999"))
    show("GET /ledger?date_from=garbage", cl.get("/ledger?date_from=garbage"))
    show("GET /ledger?view=%27%3Cscript%3E", cl.get("/ledger?view=%27%3Cscript%3E"))
    show("GET /forecast/view?horizon=abc", cl.get("/forecast/view?horizon=abc"))
    show("GET /budget/yearly?year=99999999", cl.get("/budget/yearly?year=99999999"))
    show("GET /budget?month=13", cl.get("/budget?month=13"))
    show("GET /budget?year=0&month=0", cl.get("/budget?year=0&month=0"))
    show("POST /budget/one-off/3/99999999/5", cl.post("/budget/one-off/3/99999999/5", data={"amount": "1"}, headers=H))
    show("POST /budget/one-off/3/2026/5 amount=1e400", cl.post("/budget/one-off/3/2026/5", data={"amount": "1e400"}, headers=H))
    show("POST /budget/defaults/3 amount=9e18", cl.post("/budget/defaults/3", data={"amount": "99999999999999999999"}, headers=H))
    show("POST /budget/income-anchor junk", cl.post("/budget/preferences/income-anchor", data={"category_id": "99999999999999999999"}, headers=H))
    show("POST /recurring/batch/undo junk", cl.post("/recurring/batch/undo", data={"promoted_txn_ids": "99999999999999999999"}, headers=H))
    show("POST /recurring formula source ids junk", cl.post("/recurring", data={"cadence": "monthly", "start_date": "2026-01-01", "category_id": "3", "account_id": "1", "amount_source": "formula", "terms[0][source_category_ids]": "abc", "terms[0][coefficient_percent]": "1"}, headers=H))
    show("POST /recurring/formula/preview junk", cl.post("/recurring/formula/preview", data={"amount_source": "formula", "account_id": "1", "terms[0][source_category_ids]": "abc"}, headers=H))
    show("POST /categories color junk", cl.post("/categories", data={"name": "n", "direction": "expense", "color": "javascript:x"}, headers=H))
    show("POST /categories direction junk", cl.post("/categories", data={"name": "n", "direction": "zzz"}, headers=H))
    show("POST /accounts currency junk", cl.post("/accounts", data={"name": "n", "currency": "ZZZZ"}, headers=H))
    show("POST /accounts opening_balance=1e400", cl.post("/accounts", data={"name": "n2", "currency": "PLN", "opening_balance": "1e400"}, headers=H))
    show("POST /accounts name 1MB", cl.post("/accounts", data={"name": "n" * 1_000_000, "currency": "PLN"}, headers=H))
    show("POST json body csrf header only", cl.post("/transactions", content=b"{}", headers={**H, "Content-Type": "application/json"}))
    show("GET /debug/audit-tail non-admin", cl.get("/debug/audit-tail"))
    show("GET /settings/users non-admin", cl.get("/settings/users"))
    show("GET /dev/components", cl.get("/dev/components"))
    print("== session lifecycle")
    r = cl.post("/auth/logout", headers=H)
    show("POST /auth/logout", r)
    print("  Clear-Site-Data:", r.headers.get("clear-site-data"), "| set-cookie:", [v for k, v in r.headers.multi_items() if k == "set-cookie"])
    cl.cookies.set("__Host-session", TOK)
    show("GET /today with revoked token", cl.get("/today"))
    print("== duplicate-header / host header")
    show("GET /today Host: evil.test", cl.get("/today", headers={"Host": "evil.test"}))
    show("GET / X-Forwarded-Host: evil", cl.get("/auth/login", headers={"X-Forwarded-Host": "evil.test", "X-CSP-Nonce": "attacker-nonce"}))
