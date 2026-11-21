"""Shared H2 harness: scratch DB with admin + victim V + attacker A, in-process TestClient.

Scratch DBs live under /tmp/audit-H2-*/ only. Outbound HTTP is hard-disabled
(httpx.Client.send raises) so no FX fetch can leave the machine.
Import this module BEFORE budget_planner (it sets BUDGET_DATABASE_URL).
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import httpx

_WORK = Path(tempfile.mkdtemp(prefix="audit-H2-", dir="/tmp"))
BASE = _WORK / "audit-H2-base.sqlite"
LIVE = _WORK / "audit-H2-live.sqlite"
os.environ["BUDGET_DATABASE_URL"] = f"sqlite:///{BASE}"


def _no_network(self, request, **kw):  # noqa: ANN001, ANN003, ANN202
    raise httpx.ConnectError("H2 audit: outbound HTTP disabled")


httpx.Client.send = _no_network  # type: ignore[method-assign]

from fastapi.testclient import TestClient  # noqa: E402

from budget_planner.config import Settings  # noqa: E402
from budget_planner.repositories import sessions as sessions_repo  # noqa: E402
from budget_planner.services import _passwords  # noqa: E402
from budget_planner.web.app import create_app  # noqa: E402
from budget_planner.web.auth_cookies import session_cookie_name  # noqa: E402

_passwords.DEFAULT_ROUNDS = 4
PW = "correct-horse-battery"  # pragma: allowlist secret
SENT = "VICTIMSECRET"
subprocess.run(
    [sys.executable, "-m", "budget_planner.db.startup_migrate"], check=True, capture_output=True
)


def seed() -> dict[int, dict[str, int]]:
    """users: 1 admin ADM, 2 victim V, 3 attacker A, 4 second admin ADM2; one of each record per user."""
    c = sqlite3.connect(BASE)
    c.execute("PRAGMA foreign_keys=OFF")
    pw = _passwords.hash_password(PW, rounds=4)
    c.execute("UPDATE users SET email='adm@x.test', password_hash=?, is_admin=1 WHERE id=1", (pw,))
    for uid, nm, adm in ((2, "V", 0), (3, "A", 0), (4, "ADM2", 1)):
        c.execute(
            "INSERT INTO users(id,name,email,password_hash,is_admin) VALUES (?,?,?,?,?)",
            (uid, nm, f"{nm.lower()}@x.test", pw, adm),
        )
    ids: dict[int, dict[str, int]] = {}
    for uid in (1, 2, 3, 4):
        tag = {1: "ADM", 2: SENT, 3: "ATK", 4: "ADM2"}[uid]
        d: dict[str, int] = {}

        def ins(sql: str, args: tuple) -> int:  # noqa: B023
            return c.execute(sql, args).lastrowid  # type: ignore[return-value]

        for key in ("acc", "acc2"):
            d[key] = ins(
                "INSERT INTO accounts(user_id,name,currency,opening_balance) VALUES (?,?,?,?)",
                (uid, f"{tag}-{key}", "PLN", 100000),
            )
        for key, direction in (
            ("cat_exp", "expense"),
            ("cat_exp2", "expense"),
            ("cat_inc", "income"),
            ("cat_tr", "transit"),
            ("cat_adj", "adjustment"),
        ):
            d[key] = ins(
                "INSERT INTO categories(user_id,name,direction) VALUES (?,?,?)",
                (uid, f"{tag}-{key}", direction),
            )
        d["txn"] = ins(
            "INSERT INTO transactions(user_id,operation_date,category_id,account_id,amount,description)"
            " VALUES (?,?,?,?,?,?)",
            (uid, "2026-11-10", d["cat_exp"], d["acc"], 1234, f"{tag}-txn"),
        )
        d["pl"] = ins(
            "INSERT INTO planned_transactions(user_id,operation_date,category_id,account_id,amount,description)"
            " VALUES (?,?,?,?,?,?)",
            (uid, "2026-11-01", d["cat_exp"], d["acc"], 2222, f"{tag}-pl"),
        )
        d["rule"] = ins(
            "INSERT INTO recurring_rules(user_id,cadence,start_date,category_id,account_id,default_amount,"
            "default_description,day_of_month,next_due) VALUES (?,?,?,?,?,?,?,?,?)",
            (uid, "monthly", "2026-01-01", d["cat_exp"], d["acc"], 3333, f"{tag}-rule", 5, "2026-11-05"),
        )
        c.execute(
            "INSERT INTO user_preferences(user_id,key,value) VALUES (?,?,?)",
            (uid, "income_anchor_category_id", str(d["cat_inc"])),
        )
        ids[uid] = d
    c.commit()
    c.close()
    return ids


IDS = seed()
ADM, V, A, ADM2 = IDS[1], IDS[2], IDS[3], IDS[4]
UID = {"ADM": 1, "V": 2, "A": 3, "ADM2": 4}


def fresh() -> Settings:
    for suf in ("", "-wal", "-shm"):
        Path(str(LIVE) + suf).unlink(missing_ok=True)
    shutil.copy(BASE, LIVE)
    return Settings(_env_file=None, database_url=f"sqlite:///{LIVE}", env="test")


def q(sql: str, args: tuple = ()) -> list[tuple]:
    c = sqlite3.connect(LIVE)
    try:
        return c.execute(sql, args).fetchall()
    finally:
        c.close()


def ex(sql: str, args: tuple = ()) -> None:
    c = sqlite3.connect(LIVE)
    c.execute(sql, args)
    c.commit()
    c.close()


class Sess:
    """A signed-in TestClient for one user with the CSRF header pre-wired."""

    def __init__(self, settings: Settings, uid: int) -> None:
        app = create_app(settings)
        self.cl = TestClient(app, base_url="https://testserver", follow_redirects=False)
        self.cl.__enter__()
        cn = sqlite3.connect(LIVE)
        cn.row_factory = sqlite3.Row
        self.token = sessions_repo.create_session(cn, uid, ip="127.0.0.1", user_agent="h2").token
        cn.close()
        self.cl.get("/healthz")
        self.cl.cookies.set(session_cookie_name(settings), self.token)
        self.h = {"X-CSRF-Token": self.cl.cookies.get("__Host-csrf")}

    def get(self, path: str, **kw):  # noqa: ANN003, ANN201
        return self.cl.get(path, **kw)

    def post(self, path: str, data=None, **kw):  # noqa: ANN001, ANN003, ANN201
        if isinstance(data, list):  # list of (k, v) pairs -> dict of lists (repeated fields)
            grouped: dict[str, list[str]] = {}
            for k, v in data:
                grouped.setdefault(k, []).append(v)
            data = grouped
        return self.cl.post(path, data=data or {}, headers={**self.h, **kw.pop("headers", {})}, **kw)

    def close(self) -> None:
        self.cl.__exit__(None, None, None)


def login(settings: Settings, who: str) -> Sess:
    return Sess(settings, UID[who])
