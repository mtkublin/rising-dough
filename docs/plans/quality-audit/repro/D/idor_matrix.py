"""T-Q07 Track D: runtime cross-user (IDOR) matrix.

Builds a scratch DB (migrations applied) with three users:
  1 = admin ("ADM"), 2 = victim V (non-admin), 3 = attacker A (non-admin),
seeds each with one of every user-owned record, then replays every route that
takes a record id or an id-like form field:
  control : V's own session + V's ids        (proves the payload is valid)
  attackA : A's session  + V's ids in path    (classic IDOR)
  fk      : A's session  + A's path ids + V's ids in form fields (FK injection)
  admin   : admin session + V's ids
Each case starts from a fresh copy of the seeded DB. A case is flagged when the
request is accepted (2xx), a V sentinel leaks in the body, V's rows change, A's
rows reference V-owned parents, or the server answers 5xx.

Run (scratch DB only, never data/budget.sqlite):
  uv run python docs/plans/quality-audit/repro/D/idor_matrix.py
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

WORK = Path(tempfile.mkdtemp(prefix="auditD-"))
BASE = WORK / "base.sqlite"
LIVE = WORK / "live.sqlite"
SENT = "VICTIMSECRET"
os.environ["BUDGET_DATABASE_URL"] = f"sqlite:///{BASE}"

from fastapi.testclient import TestClient  # noqa: E402

from budget_planner.config import Settings  # noqa: E402
from budget_planner.repositories import sessions as sessions_repo  # noqa: E402
from budget_planner.services import _passwords  # noqa: E402
from budget_planner.web.app import create_app  # noqa: E402
from budget_planner.web.auth_cookies import session_cookie_name  # noqa: E402

_passwords.DEFAULT_ROUNDS = 4
subprocess.run(
    [sys.executable, "-m", "budget_planner.db.startup_migrate"], check=True, capture_output=True
)


def seed() -> dict[str, dict[str, int]]:
    c = sqlite3.connect(BASE)
    c.execute("PRAGMA foreign_keys=OFF")
    pw = _passwords.hash_password("correct-horse-battery", rounds=4)
    c.execute("UPDATE users SET email='adm@x.test', password_hash=?, is_admin=1 WHERE id=1", (pw,))
    for uid, nm in ((2, "V"), (3, "A")):
        c.execute(
            "INSERT INTO users(id,name,email,password_hash,is_admin) VALUES (?,?,?,?,0)",
            (uid, nm, f"{nm.lower()}@x.test", pw),
        )
    ids: dict[str, dict[str, int]] = {}
    for uid in (1, 2, 3):
        tag = {1: "ADM", 2: SENT, 3: "ATK"}[uid]
        d: dict[str, int] = {}

        def ins(sql: str, args: tuple) -> int:  # noqa: B023
            return c.execute(sql, args).lastrowid  # type: ignore[return-value]

        for key, nm in (("acc", "acc1"), ("acc2", "acc2")):
            d[key] = ins(
                "INSERT INTO accounts(user_id,name,currency,opening_balance) VALUES (?,?,?,?)",
                (uid, f"{tag}-{nm}", "PLN", 100000),
            )
        for key, direction in (
            ("cat_exp", "expense"),
            ("cat_inc", "income"),
            ("cat_tr", "transit"),
            ("cat_adj", "adjustment"),
        ):
            d[key] = ins(
                "INSERT INTO categories(user_id,name,direction) VALUES (?,?,?)",
                (uid, f"{tag}-{direction}", direction),
            )
        d["txn"] = ins(
            "INSERT INTO transactions(user_id,operation_date,category_id,account_id,amount,description)"
            " VALUES (?,?,?,?,?,?)",
            (uid, "2026-11-10", d["cat_exp"], d["acc"], 1234, f"{tag}-txn"),
        )
        d["txn_del"] = ins(
            "INSERT INTO transactions(user_id,operation_date,category_id,account_id,amount,description,deleted_at)"
            " VALUES (?,?,?,?,?,?,'2026-11-11T00:00:00.000Z')",
            (uid, "2026-11-10", d["cat_exp"], d["acc"], 777, f"{tag}-txn-del"),
        )
        d["pl"] = ins(
            "INSERT INTO planned_transactions(user_id,operation_date,category_id,account_id,amount,description)"
            " VALUES (?,?,?,?,?,?)",
            (uid, "2026-11-01", d["cat_exp"], d["acc"], 2222, f"{tag}-pl"),
        )
        d["pl_del"] = ins(
            "INSERT INTO planned_transactions(user_id,operation_date,category_id,account_id,amount,description,deleted_at)"
            " VALUES (?,?,?,?,?,?,'2026-11-11T00:00:00.000Z')",
            (uid, "2026-11-01", d["cat_exp"], d["acc"], 2223, f"{tag}-pl-del"),
        )
        d["rule"] = ins(
            "INSERT INTO recurring_rules(user_id,cadence,start_date,category_id,account_id,default_amount,"
            "default_description,day_of_month,next_due) VALUES (?,?,?,?,?,?,?,?,?)",
            (uid, "monthly", "2026-01-01", d["cat_exp"], d["acc"], 3333, f"{tag}-rule", 5, "2026-11-05"),
        )
        c.execute(
            "INSERT INTO recurring_rule_overrides(rule_id,occurrence_date,state) VALUES (?,?,?)",
            (d["rule"], "2026-12-05", "skipped"),
        )
        d["snap"] = ins(
            "INSERT INTO account_snapshots(account_id,balance,note) VALUES (?,?,?)",
            (d["acc"], 4444, f"{tag}-snap"),
        )
        ins(
            "INSERT INTO budget_defaults(user_id,category_id,amount) VALUES (?,?,?)",
            (uid, d["cat_exp"], 5555),
        )
        ins(
            "INSERT INTO budget_recurring_overrides(user_id,category_id,month,amount) VALUES (?,?,?,?)",
            (uid, d["cat_exp"], 3, 6666),
        )
        ins(
            "INSERT INTO budget_one_off_overrides(user_id,category_id,year,month,amount) VALUES (?,?,?,?,?)",
            (uid, d["cat_exp"], 2026, 4, 7777),
        )
        d["cred"] = ins(
            "INSERT INTO webauthn_credentials(user_id,credential_id,public_key,label) VALUES (?,?,?,?)",
            (uid, f"cred{uid}".encode(), b"pk", f"{tag}-key"),
        )
        # income anchor preference for every user so cross-user writes are visible
        c.execute(
            "INSERT INTO user_preferences(user_id,key,value) VALUES (?,?,?)",
            (uid, "income_anchor_category_id", str(d["cat_inc"])),
        )
        ids[str(uid)] = d
    c.commit()
    c.close()
    return ids


IDS = seed()
V, A, ADM = IDS["2"], IDS["3"], IDS["1"]


def fresh() -> Settings:
    for suf in ("", "-wal", "-shm"):
        Path(str(LIVE) + suf).unlink(missing_ok=True)
    shutil.copy(BASE, LIVE)
    return Settings(_env_file=None, database_url=f"sqlite:///{LIVE}", env="test")


def session_for(settings: Settings, uid: int) -> tuple[str, str, str]:
    c = sqlite3.connect(LIVE)
    c.row_factory = sqlite3.Row
    tok = sessions_repo.create_session(c, uid, ip="127.0.0.1", user_agent="audit").token
    c.close()
    return session_cookie_name(settings), tok, sessions_repo.session_handle(tok)


def snapshot(uids: tuple[int, ...]) -> dict[str, str]:
    c = sqlite3.connect(LIVE)
    out = {}
    marks = ",".join(map(str, uids))
    for t in (
        "accounts",
        "categories",
        "transactions",
        "planned_transactions",
        "recurring_rules",
        "budget_defaults",
        "budget_recurring_overrides",
        "budget_one_off_overrides",
        "user_preferences",
        "webauthn_credentials",
    ):
        rows = c.execute(f"SELECT * FROM {t} WHERE user_id IN ({marks}) ORDER BY id").fetchall()  # noqa: S608
        out[t] = hashlib.sha1(repr(rows).encode()).hexdigest()  # noqa: S324
    rows = c.execute(f"SELECT id,name,email,password_hash,is_admin,deleted_at FROM users WHERE id IN ({marks})").fetchall()  # noqa: S608
    out["users"] = hashlib.sha1(repr(rows).encode()).hexdigest()  # noqa: S324
    for t in ("recurring_rule_overrides", "account_snapshots"):
        out[t] = hashlib.sha1(repr(c.execute(f"SELECT * FROM {t} ORDER BY id").fetchall()).encode()).hexdigest()  # noqa: S608,S324
    out["sessions_alive"] = repr(
        c.execute(f"SELECT user_id,count(*) FROM sessions WHERE revoked_at IS NULL AND user_id IN ({marks}) GROUP BY 1").fetchall()  # noqa: S608
    )
    c.close()
    return out


def xref_violations(victim: dict[str, int], attacker_uid: int) -> list[str]:
    """Attacker-owned rows that reference victim-owned parents."""
    c = sqlite3.connect(LIVE)
    vacc = f"({victim['acc']},{victim['acc2']})"
    vcat = f"({victim['cat_exp']},{victim['cat_inc']},{victim['cat_tr']},{victim['cat_adj']})"
    out = []
    for t in ("transactions", "planned_transactions", "recurring_rules"):
        r = c.execute(
            f"SELECT id FROM {t} WHERE user_id={attacker_uid} AND "  # noqa: S608
            f"(account_id IN {vacc} OR dest_account_id IN {vacc} OR category_id IN {vcat})"
        ).fetchall()
        if r:
            out.append(f"{t}:{[x[0] for x in r]}")
    for t in ("budget_defaults", "budget_recurring_overrides", "budget_one_off_overrides"):
        r = c.execute(f"SELECT id FROM {t} WHERE user_id={attacker_uid} AND category_id IN {vcat}").fetchall()  # noqa: S608
        if r:
            out.append(f"{t}:{[x[0] for x in r]}")
    r = c.execute(f"SELECT id FROM account_snapshots WHERE account_id IN {vacc} AND note NOT LIKE '%{SENT}%'").fetchall()  # noqa: S608
    if r:
        out.append(f"snapshot-on-victim-account:{[x[0] for x in r]}")
    c.close()
    return out


def routes(o: dict[str, int], r: dict[str, int], victim_handle: str) -> list[tuple[str, str, dict | None]]:
    """(method, path, form). `o` supplies path ids, `r` supplies ids placed in form fields."""
    txn = {
        "operation_date": "2026-11-12",
        "category_id": str(r["cat_exp"]),
        "account_id": str(r["acc"]),
        "amount": "12.50",
        "description": "x",
    }
    transit = {**txn, "category_id": str(r["cat_tr"]), "dest_account_id": str(r["acc2"])}
    rule = {
        "cadence": "monthly",
        "start_date": "2026-01-01",
        "category_id": str(r["cat_exp"]),
        "account_id": str(r["acc"]),
        "default_amount": "9.00",
        "default_description": "r",
        "day_of_month": "5",
        "amount_source": "fixed",
    }
    return [
        ("GET", f"/transactions/{o['txn']}/edit", None),
        ("POST", f"/transactions/{o['txn']}", txn),
        ("POST", f"/transactions/{o['txn']}", transit),
        ("POST", f"/transactions/{o['txn']}/delete", {}),
        ("POST", f"/transactions/{o['txn_del']}/restore", {}),
        ("POST", "/transactions", txn),
        ("POST", "/transactions", transit),
        ("GET", f"/accounts/{o['acc']}/edit", None),
        ("POST", f"/accounts/{o['acc']}", {"name": "renamed", "type": "checking"}),
        ("POST", f"/accounts/{o['acc']}/delete", {}),
        ("POST", f"/accounts/{o['acc']}/snapshot", {}),
        ("GET", f"/accounts/{o['acc']}/reconcile", None),
        (
            "POST",
            f"/accounts/{o['acc']}/reconcile",
            {"actual_balance": "500.00", "category_id": str(r["cat_adj"]), "save_snapshot": "on"},
        ),
        ("GET", f"/categories/{o['cat_exp']}/edit", None),
        ("POST", f"/categories/{o['cat_exp']}", {"name": "renamed"}),
        ("POST", f"/categories/{o['cat_exp']}/archive", {}),
        ("POST", f"/categories/{o['cat_exp']}/delete", {}),
        ("POST", f"/categories/{o['cat_exp']}/restore", {}),
        ("GET", f"/planned/{o['pl']}/edit", None),
        ("POST", f"/planned/{o['pl']}", txn),
        ("POST", f"/planned/{o['pl']}/delete", {}),
        ("POST", f"/planned/{o['pl_del']}/restore", {}),
        ("POST", "/planned", txn),
        ("POST", "/planned", transit),
        ("GET", f"/planned/{o['pl']}/promote", None),
        ("GET", f"/planned/{o['pl']}/promote/inline", None),
        (
            "POST",
            f"/planned/{o['pl']}/promote",
            {"operation_date": "2026-11-12", "amount": "22.00", "description": "p"},
        ),
        (
            "POST",
            "/planned/batch/undo",
            {"promoted_txn_ids": str(o["txn"]), "promoted_planned_ids": str(o["pl"])},
        ),
        ("GET", f"/recurring/{o['rule']}/edit", None),
        ("POST", "/recurring", rule),
        ("POST", f"/recurring/{o['rule']}", rule),
        ("POST", f"/recurring/{o['rule']}/deactivate", {}),
        ("POST", f"/recurring/{o['rule']}/skip-next", {}),
        ("GET", f"/recurring/{o['rule']}/overrides/new", None),
        ("POST", f"/recurring/{o['rule']}/overrides", {"year": "2026", "month": "12", "amount": "1.00"}),
        ("POST", f"/recurring/{o['rule']}/overrides/2026-12-05/delete", {}),
        ("GET", f"/recurring/{o['rule']}/promote", None),
        ("GET", f"/recurring/{o['rule']}/promote/inline", None),
        (
            "POST",
            f"/recurring/{o['rule']}/promote",
            {"operation_date": "2026-11-12", "amount": "3.00", "description": "p"},
        ),
        (
            "POST",
            "/recurring/batch/undo",
            {"promoted_txn_ids": str(o["txn"]), "advanced_rule_ids": str(o["rule"])},
        ),
        (
            "POST",
            "/recurring/formula/preview",
            {
                "amount_source": "formula",
                "account_id": str(r["acc"]),
                "terms[0][sign]": "+",
                "terms[0][coefficient_percent]": "10",
                "terms[0][source_category_ids]": str(r["cat_exp"]),
            },
        ),
        ("GET", f"/budget/rules/{o['cat_exp']}/overrides/new", None),
        ("POST", f"/budget/rules/{o['cat_exp']}/overrides", {"tier": "default", "amount": "1.00"}),
        ("POST", f"/budget/defaults/{o['cat_exp']}", {"amount": "1.00"}),
        ("POST", f"/budget/recurring/{o['cat_exp']}/5", {"amount": "1.00"}),
        ("POST", f"/budget/one-off/{o['cat_exp']}/2026/5", {"amount": "1.00"}),
        ("POST", "/budget/preferences/income-anchor", {"category_id": ""}),
        ("POST", f"/auth/passkeys/{o['cred']}/revoke", {}),
        ("POST", f"/auth/sessions/{victim_handle}/revoke", {}),
        ("GET", f"/settings/users/{o['uid']}/edit", None),
        ("POST", f"/settings/users/{o['uid']}", {"email": "evil@x.test", "name": "evil"}),
        ("POST", f"/settings/users/{o['uid']}/reset-password", {}),
        ("POST", f"/settings/users/{o['uid']}/delete", {}),
        ("GET", f"/ledger?q=zzqq", None),
        ("GET", f"/ledger/table?view=actual&account_id={r['acc']}&category_id={r['cat_exp']}", None),
        ("GET", f"/transactions/export?account_id={r['acc']}", None),
        ("GET", f"/planned/export?account_id={r['acc']}", None),
        ("GET", f"/transactions/_limit_preview?account_id={r['acc']}&amount=1&operation_date=2026-11-12", None),
        ("GET", f"/forecast/view?account_id={r['acc']}", None),
        ("GET", f"/today/afford?account_id={r['acc']}&amount=10", None),
        ("GET", f"/accounts/last-checked?account_id={r['acc']}", None),
    ]


def run_case(mode: str, actor: int, owner: dict, refs: dict, vuid: int) -> list[tuple]:
    results = []
    count = len(routes({**owner, "uid": vuid}, refs, "0" * 16))
    for i in range(count):
        settings = fresh()
        app = create_app(settings)
        cname, tok, _h = session_for(settings, actor)
        _n, _t, vhandle = session_for(settings, vuid)
        method, path, data = routes({**owner, "uid": vuid}, refs, vhandle)[i]
        before = snapshot((vuid,) if actor != vuid else (vuid,))
        with TestClient(app, base_url="https://testserver", follow_redirects=False) as cl:
            cl.get("/healthz")
            cl.cookies.set(cname, tok)
            hdr = {"X-CSRF-Token": cl.cookies.get("__Host-csrf") or ""}
            try:
                resp = (
                    cl.request(method, path, data=data, headers=hdr)
                    if method == "POST"
                    else cl.get(path)
                )
                code, body = resp.status_code, resp.text
            except Exception as exc:  # noqa: BLE001
                code, body = 599, f"EXC {type(exc).__name__}: {exc}"
        after = snapshot((vuid,))
        changed = [k for k in before if before[k] != after[k]]
        leak = SENT in body
        xref = xref_violations(V, 3) if actor == 3 else []
        keep = {k: v for k, v in (data or {}).items() if k.endswith("_id") or k in ("name", "tier")}
        results.append((mode, method, path, keep, code, leak, changed, xref))
    return results


if __name__ == "__main__":
    out: list[tuple] = []
    out += run_case("control", 2, V, V, 2)  # V on own records: payloads must be valid
    out += run_case("attackA", 3, V, A, 2)  # A on V's path ids
    out += run_case("fk", 3, A, V, 3)  # A on own path ids, V's ids in form fields
    out += run_case("admin", 1, V, ADM, 2)  # admin on V's ids
    for mode, method, path, keep, code, leak, changed, xref in out:
        flag = ""
        if mode != "control" and (200 <= code < 300 or leak or changed or xref or code >= 500):
            flag = "  <== REVIEW"
        print(f"{mode}\t{method}\t{path}\t{keep}\t{code}\tleak={leak}\tVchanged={changed}\txref={xref}{flag}")
    print("workdir", WORK)
