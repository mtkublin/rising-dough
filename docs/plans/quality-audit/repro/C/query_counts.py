"""T-Q06 query-count harness. Scratch DB only (never data/budget.sqlite).

Usage (from repo root):
    cp data/demo.sqlite /tmp/audit-C.sqlite
    BUDGET_DATABASE_URL=sqlite:////tmp/audit-C.sqlite uv run python -m budget_planner.db.migrate
    BUDGET_DATABASE_URL=sqlite:////tmp/audit-C.sqlite PYTHONPATH=. \
        uv run python docs/plans/quality-audit/repro/C/query_counts.py
"""

from __future__ import annotations

import collections
import os
import re
import sqlite3
import sys
import time

URL = os.environ.get("BUDGET_DATABASE_URL", "")
if not URL.startswith("sqlite:////tmp/") or "budget.sqlite" in URL:
    sys.exit("refusing: BUDGET_DATABASE_URL must point at a /tmp scratch DB")

LOG: list[str] = []
_real_connect = sqlite3.connect


def _traced_connect(*args, **kwargs):  # type: ignore[no-untyped-def]
    conn = _real_connect(*args, **kwargs)
    conn.set_trace_callback(LOG.append)
    return conn


sqlite3.connect = _traced_connect  # type: ignore[assignment]

from fastapi.testclient import TestClient  # noqa: E402

from budget_planner.config import Settings  # noqa: E402
from budget_planner.web.app import create_app  # noqa: E402
from tests.auth_support import login_cookie  # noqa: E402

ID_TABLE = {
    "account_id": "accounts",
    "category_id": "categories",
    "txn_id": "transactions",
    "planned_id": "planned_transactions",
    "rule_id": "recurring_rules",
    "user_id": "users",
}
NOISE = re.compile(r"^\s*(PRAGMA|BEGIN|COMMIT|ROLLBACK|SAVEPOINT|RELEASE)", re.I)


def norm(sql: str) -> str:
    sql = re.sub(r"'[^']*'", "?", sql)
    return re.sub(r"\b\d+\b", "?", sql).strip()[:160]


def main() -> None:
    settings = Settings()
    app = create_app(settings)
    peek = _real_connect(URL.removeprefix("sqlite:///"))
    ids = {}
    for p, t in ID_TABLE.items():
        if t == "users":
            ids[p] = 1
            continue
        row = peek.execute(f"SELECT id FROM {t} WHERE user_id=1 LIMIT 1").fetchone()  # noqa: S608
        ids[p] = row[0] if row else 1
    import importlib  # noqa: PLC0415

    from budget_planner.web.app import _ROUTER_NAMES  # noqa: PLC0415

    found: set[str] = set()
    for rname in _ROUTER_NAMES:
        mod = importlib.import_module(f"budget_planner.web.routers.{rname}")
        for r in mod.router.routes:
            if "GET" in (getattr(r, "methods", None) or ()):
                found.add(r.path)  # type: ignore[attr-defined]
    routes = sorted(found)
    name, value = login_cookie(settings)
    print(f"{'route':45} {'status':>6} {'queries':>7} {'ms':>6} {'max-repeat':>10}")
    with TestClient(app, base_url="https://testserver") as client:
        client.cookies.set(name, value)
        for path in routes:
            if path.startswith(("/static", "/docs", "/openapi", "/redoc")):
                continue
            url = re.sub(r"\{(\w+)\}", lambda m: str(ids.get(m.group(1), 1)), path)
            LOG.clear()
            t0 = time.perf_counter()
            resp = client.get(url, follow_redirects=False)
            ms = (time.perf_counter() - t0) * 1000
            stmts = [norm(s) for s in LOG if not NOISE.match(s)]
            top = collections.Counter(stmts).most_common(1)
            rep = top[0][1] if top else 0
            print(f"{url:45} {resp.status_code:>6} {len(stmts):>7} {ms:>6.0f} {rep:>10}")
            if rep >= 5:
                print(f"    repeated x{rep}: {top[0][0]}")
            if url in sys.argv[1:]:
                for stmt, n in collections.Counter(stmts).most_common(int(os.environ.get('TOPN', '6'))):
                    print(f"      {n:>5}x {stmt}")


if __name__ == "__main__":
    main()
