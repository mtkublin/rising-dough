"""H2 admin/privilege chains (scratch DB, in-process).

1. non-admin -> admin via any form field (mass assignment) on every writable form.
2. admin self-demotion / self-delete / last-admin; edit-form without the is_admin field.
3. two admins removing each other concurrently (barrier forced between the last-admin count and the
   write) -> is the 'at least one admin' invariant preserved, and what does the loser see?

Run: uv run python docs/plans/quality-audit/repro/H2/h2_04_admin_chain.py | grep -v '^{"event"'
"""

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _harness import PW, A, V, ex, fresh, login, q  # noqa: E402

from budget_planner.db.connection import get_connection  # noqa: E402
from budget_planner.services import users as users_svc  # noqa: E402


def admins() -> list:
    return q("select id,is_admin,deleted_at is not null from users order by id")


print("== 1. mass assignment as non-admin A (id 3)")
s = fresh()
a = login(s, "A")
extra = {"is_admin": "1", "is_admin_": "on", "user_id": "3", "role": "admin"}
for path, data in (
    ("/settings/users/3", {"email": "a@x.test", "name": "A", **extra}),
    ("/settings/users", {"email": "n@x.test", "name": "n", "is_admin": "on"}),
    ("/settings/users/3/reset-password", {}),
    ("/settings/password", {"current_password": PW, "new_password": "newpass-123456789", "confirm_password": "newpass-123456789", **extra}),  # pragma: allowlist secret
    ("/accounts", {"name": "x", "currency": "PLN", **extra}),
    ("/categories", {"name": "x", "direction": "expense", **extra}),
):
    r = a.post(path, data)
    print(f"  POST {path:34s} -> {r.status_code}")
print("  users after:", admins())
print("  GET /settings/users ->", a.get("/settings/users").status_code, "| /debug/audit-tail ->", a.get("/debug/audit-tail").status_code)

print("== 2. admin self-service (admins: 1 ADM, 4 ADM2)")
s = fresh()
adm = login(s, "ADM")
r = adm.post("/settings/users/1/delete")
print("  ADM deletes self ->", r.status_code, admins()[0])
r = adm.post("/settings/users/1", {"email": "adm@x.test", "name": "ADM"})  # is_admin omitted == unchecked
print("  ADM saves self WITHOUT is_admin field (self-demotion, other admin exists) ->", r.status_code, admins())
print("  ADM next request to /settings/users ->", adm.get("/settings/users").status_code, "(demotion applies at once)")
adm2 = login(s, "ADM2")
r = adm2.post("/settings/users/4", {"email": "adm2@x.test", "name": "ADM2"})
print("  ADM2 (now last admin) demotes self ->", r.status_code, admins())
r = adm2.post("/settings/users/4/delete")
print("  ADM2 deletes self ->", r.status_code)
# a different admin edits ANOTHER admin's profile via a client that omits the checkbox
s = fresh()
adm = login(s, "ADM")
r = adm.post("/settings/users/4", {"email": "adm2@x.test", "name": "renamed"})
print("  ADM renames ADM2 without is_admin field ->", r.status_code, admins(), "<== ADM2 silently demoted")

print("== 3. concurrent mutual removal of the only two admins")
s = fresh()
c1, c2 = get_connection(s), get_connection(s)
bar = threading.Barrier(2)
orig = users_svc._is_last_admin


def gated(conn, user):  # noqa: ANN001, ANN202
    res = orig(conn, user)  # reads count inside the open transaction (snapshot taken here)
    try:
        bar.wait(timeout=5)  # both transactions now hold a snapshot showing 2 admins
    except threading.BrokenBarrierError:
        pass
    return res


users_svc._is_last_admin = gated  # type: ignore[assignment]
out: dict[str, str] = {}


def run(name: str, conn, actor: int, target: int) -> None:  # noqa: ANN001
    try:
        users_svc.soft_delete_user(conn, actor, target)
        out[name] = "ok"
    except Exception as exc:  # noqa: BLE001
        out[name] = f"{type(exc).__name__}: {exc}"


t1 = threading.Thread(target=run, args=("ADM deletes ADM2", c1, 1, 4))
t2 = threading.Thread(target=run, args=("ADM2 deletes ADM", c2, 4, 1))
t1.start(); t2.start(); t1.join(); t2.join()
users_svc._is_last_admin = orig  # type: ignore[assignment]
for k, v in out.items():
    print(f"  {k}: {v}")
print("  live admins afterwards:", q("select count(*) from users where is_admin=1 and deleted_at is null")[0][0], admins())
