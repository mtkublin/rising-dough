"""D-01 repro: POST /budget/preferences/income-anchor always writes user_id=1.

Also probes read-side filters (account_id / category_id query params) with another user's ids.
Scratch DB only. Run: uv run python docs/plans/quality-audit/repro/D/income_anchor_cross_user.py
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

WORK = Path(tempfile.mkdtemp(prefix="auditD01-"))
DB = WORK / "d01.sqlite"
os.environ["BUDGET_DATABASE_URL"] = f"sqlite:///{DB}"

from fastapi.testclient import TestClient  # noqa: E402

from budget_planner.config import Settings  # noqa: E402
from budget_planner.repositories import sessions as sessions_repo  # noqa: E402
from budget_planner.services import _passwords  # noqa: E402
from budget_planner.web.app import create_app  # noqa: E402

subprocess.run([sys.executable, "-m", "budget_planner.db.startup_migrate"], check=True, capture_output=True)
c = sqlite3.connect(DB)
pw = _passwords.hash_password("correct-horse-battery", rounds=4)
c.execute("UPDATE users SET email='owner@x.test', password_hash=? WHERE id=1", (pw,))
c.execute("INSERT INTO users(id,name,email,password_hash) VALUES (2,'second','second@x.test',?)", (pw,))
cat1 = c.execute("INSERT INTO categories(user_id,name,direction) VALUES (1,'OWNER-salary','income')").lastrowid
cat2 = c.execute("INSERT INTO categories(user_id,name,direction) VALUES (2,'SECOND-salary','income')").lastrowid
acc1 = c.execute("INSERT INTO accounts(user_id,name,currency,opening_balance) VALUES (1,'OWNER-acc','PLN',123456)").lastrowid
c.execute("INSERT INTO transactions(user_id,operation_date,category_id,account_id,amount,description) VALUES (1,'2026-11-10',?,?,999,'OWNER-SECRET-txn')", (cat1, acc1))
c.execute("INSERT INTO user_preferences(user_id,key,value) VALUES (1,'income_anchor_category_id',?)", (str(cat1),))
c.commit()
settings = Settings(_env_file=None, database_url=f"sqlite:///{DB}", env="test")
app = create_app(settings)
cn = sqlite3.connect(DB)
cn.row_factory = sqlite3.Row
tok2 = sessions_repo.create_session(cn, 2, ip="127.0.0.1", user_agent="p").token
cn.close()


def prefs() -> list[tuple]:
    k = sqlite3.connect(DB)
    rows = k.execute("SELECT user_id,key,value FROM user_preferences ORDER BY user_id").fetchall()
    k.close()
    return rows


print("before:", prefs(), f"(owner cat={cat1}, second cat={cat2})")
with TestClient(app, base_url="https://testserver", follow_redirects=False) as cl:
    cl.get("/healthz")
    cl.cookies.set("__Host-session", tok2)
    h = {"X-CSRF-Token": cl.cookies.get("__Host-csrf")}
    r = cl.post("/budget/preferences/income-anchor", data={"category_id": str(cat2)}, headers=h)
    print("second user sets own category as anchor ->", r.status_code, r.text[:80], "| prefs:", prefs())
    r = cl.post("/budget/preferences/income-anchor", data={"category_id": ""}, headers=h)
    print("second user CLEARS anchor            ->", r.status_code, "| prefs:", prefs(), "<== owner's preference deleted by another user")
    # read-side: another user's ids in query filters
    for path in (
        f"/transactions/export?account_id={acc1}",
        f"/ledger/table?view=actual&account_id={acc1}&category_id={cat1}",
        f"/forecast/view?account_id={acc1}",
        f"/today/afford?account_id={acc1}&amount=10",
        f"/transactions/_limit_preview?account_id={acc1}&amount=1&operation_date=2026-11-12",
        f"/accounts/last-checked?account_id={acc1}",
        f"/ledger?account_id={acc1}&q=OWNER",
    ):
        r = cl.get(path)
        leaked = any(s in r.text for s in ("OWNER-SECRET", "OWNER-acc", "123456", "1234.56", "1 234,56", "OWNER-salary"))
        print(f"GET {path[:70]:70s} -> {r.status_code} leak={leaked}")
