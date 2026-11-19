"""H3: session fixation / replay / rotation, re-auth window and bypass attempts, forced-rotation gate.

Run: uv run python docs/plans/quality-audit/repro/H3/h3_sessions_reauth.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import PW, SESSION, client, db_exec, fresh_reauth, hdr, login, make_app, new_db, prime, say  # noqa: E402

db = new_db("sessions")
BIG = {
    f"rate_limit_{k}": 500
    for k in ("reauth_per_minute", "reauth_per_hour", "login_per_minute", "login_per_hour",
              "login_ip_per_hour", "password_change_per_minute", "password_change_per_hour")
}
app, settings = make_app(db, **BIG)
NOW = {"t": None}
app.state.reauth_clock = lambda: NOW["t"] or datetime.now(UTC)


def ck(cl, name):
    """Last cookie value with *name* in the jar (planted + server cookies can coexist)."""
    vals = [c.value for c in cl.cookies.jar if c.name == name]
    return vals[-1] if vals else None


def live(uid):
    return db_exec(db, "SELECT count(*) FROM sessions WHERE user_id=? AND revoked_at IS NULL", (uid,))[0][0]


# ---- S1 fixation: attacker plants a session cookie value before victim logs in ------------
say("== S1 fixation: pre-planted session cookie value before login")
victim = client(app)
prime(victim)
victim.cookies.set(SESSION, "ATTACKER_CHOSEN_TOKEN_VALUE_000000000000000000", domain="testserver.local")
r = login(victim)
tok = ck(victim, SESSION)
say("login ->", r.status_code, "| cookie after login equals planted value:", tok == "ATTACKER_CHOSEN_TOKEN_VALUE_000000000000000000")
planted = client(app)
planted.cookies.set(SESSION, "ATTACKER_CHOSEN_TOKEN_VALUE_000000000000000000", domain="testserver.local")
say("planted value usable by attacker: GET /today ->", planted.get("/today").status_code)

# ---- S2 theft + replay after logout / password change / reauth rotation ---------------------
say("\n== S2 replay of a copied session token")
v = client(app); login(v); stolen = ck(v, SESSION)
thief = client(app); thief.cookies.set(SESSION, stolen, domain="testserver.local")
say("thief before logout: /today ->", thief.get("/today").status_code)
v.post("/auth/logout", headers=hdr(v))
say("thief after victim logout ->", thief.get("/today").status_code)

v = client(app); login(v); stolen = ck(v, SESSION)
thief = client(app); thief.cookies.set(SESSION, stolen, domain="testserver.local")
r = v.post("/settings/password", data={"current_password": PW, "new_password": PW + "-new", "confirm_password": PW + "-new", "_csrf_token": v.cookies.get(CSRF := "__Host-csrf")})
say("password change ->", r.status_code, "| stolen token after change ->", thief.get("/today").status_code, "| victim rotated cookie works ->", v.get("/today").status_code)
PW2 = PW + "-new"

v = client(app); login(v, password=PW2); stolen = ck(v, SESSION)
thief = client(app); thief.cookies.set(SESSION, stolen, domain="testserver.local")
fresh_reauth_pw = lambda cl, pw: cl.post("/auth/reauth", data={"password": pw, "next": "/", "_csrf_token": cl.cookies.get("__Host-csrf")})
r = fresh_reauth_pw(v, PW2)
say("reauth ->", r.status_code, "| pre-rotation token still valid ->", thief.get("/today").status_code)

# ---- S3 reauth window -------------------------------------------------------------------------
say("\n== S3 re-auth window and HTMX / JSON shapes")
v = client(app); login(v, password=PW2)
r = v.post("/auth/passkeys/1/revoke", headers=hdr(v))
say("fresh login, guarded route ->", r.status_code, "(404 = passed guard, no such passkey)")
NOW["t"] = datetime.now(UTC) + timedelta(minutes=11)
r = v.post("/auth/passkeys/1/revoke", headers=hdr(v))
say("t+11min plain POST ->", r.status_code, r.headers.get("location"))
r = v.post("/auth/passkeys/1/revoke", headers=hdr(v, **{"HX-Request": "true"}))
say("t+11min HX-Request ->", r.status_code, r.headers.get("hx-redirect"))
r = v.post("/auth/register/begin", headers=hdr(v, Accept="application/json"))
say("t+11min register/begin JSON ->", r.status_code, r.text)
# every guarded route, stale session
for path in ("/auth/register/finish", "/settings/users", "/settings/users/2", "/settings/users/2/reset-password", "/settings/users/2/delete"):
    r = v.post(path, headers=hdr(v))
    say(f"  stale POST {path} ->", r.status_code)
# stale session reaches `GET /auth/reauth` and can re-auth: new authenticated_at
NOW["t"] = None
# attacker with stolen stale session and *no* password
sess = ck(v, SESSION)
db_exec(db, "UPDATE sessions SET authenticated_at='2000-01-01T00:00:00.000000Z'")
thief = client(app); thief.cookies.set(SESSION, ck(v, SESSION), domain="testserver.local"); prime(thief)
r = thief.post("/auth/passkeys/1/revoke", headers=hdr(thief))
say("stale stolen session -> guarded route ->", r.status_code, r.headers.get("location"))
r = thief.post("/auth/reauth", data={"password": "wrong-password-xx", "next": "/", "_csrf_token": thief.cookies.get("__Host-csrf")})
say("stale stolen session -> reauth with wrong password ->", r.status_code)
# reauth `next` open redirect
r = thief.post("/auth/reauth", data={"password": PW2, "next": "//evil.example/x", "_csrf_token": thief.cookies.get("__Host-csrf")})
say("reauth next=//evil.example/x ->", r.status_code, r.headers.get("location"))

# ---- S4 forced-rotation gate ------------------------------------------------------------------
say("\n== S4 must_change_password gate: which state-changing routes answer?")
db_exec(db, "UPDATE users SET must_change_password=1 WHERE id=3")
a = client(app)
r = login(a, "a@x.test", PW)
say("flagged login ->", r.status_code)
routes = [
    ("POST", "/auth/reauth"), ("POST", "/auth/reauth/begin"), ("POST", "/auth/reauth/finish"),
    ("POST", "/auth/register/begin"), ("POST", "/auth/register/finish"), ("POST", "/auth/passkeys/1/revoke"),
    ("POST", "/auth/sessions/aaaaaaaaaaaaaaaa/revoke"), ("POST", "/transactions"), ("POST", "/accounts"),
    ("POST", "/settings/password"), ("GET", "/today"), ("GET", "/auth/reauth"),
    ("GET", "/auth/sessions"), ("GET", "/auth/register"), ("POST", "/auth/login/begin"), ("POST", "/auth/logout"),
]
for m, p in routes:
    rr = a.request(m, p, headers=hdr(a), data={})
    say(f"  {m:4} {p:42} -> {rr.status_code} {rr.headers.get('location', '')}")
# bypass via path normalisation
for p in ("/settings/password/", "//settings/password", "/Settings/password", "/settings/password/../../transactions", "/static/../transactions"):
    rr = a.request("GET", p)
    say(f"  GET {p:42} -> {rr.status_code} {rr.headers.get('location', '')}")
db_exec(db, "UPDATE users SET must_change_password=0 WHERE id=3")

# ---- S5 privilege change applies at once -------------------------------------------------------
say("\n== S5 demotion / soft-delete of the user invalidates live sessions immediately")
adm = client(app); login(adm, "adm@x.test", PW)
say("admin GET /settings/users ->", adm.get("/settings/users").status_code)
db_exec(db, "UPDATE users SET is_admin=0 WHERE id=1")
say("after demotion GET /settings/users ->", adm.get("/settings/users").status_code)
db_exec(db, "UPDATE users SET is_admin=1 WHERE id=1")
db_exec(db, "UPDATE users SET deleted_at='2026-01-01T00:00:00.000000Z' WHERE id=3")
a = client(app)
say("deleted user login ->", login(a, "a@x.test").status_code, "(401 = generic failure)")
db_exec(db, "UPDATE users SET deleted_at=NULL WHERE id=3")

# ---- S6 expiry: absolute cap ---------------------------------------------------------------------
say("\n== S6 absolute lifetime cap holds across re-auth rotation")
v = client(app); login(v, password=PW2)
db_exec(db, "UPDATE sessions SET created_at='2020-01-01T00:00:00.000000Z' WHERE id=(SELECT id FROM sessions WHERE user_id=2 AND revoked_at IS NULL ORDER BY rowid DESC LIMIT 1)")
db_exec(db, "UPDATE sessions SET expires_at='2099-01-01T00:00:00.000000Z' WHERE user_id=2 AND created_at='2020-01-01T00:00:00.000000Z'")
r = v.get("/today")
say("session older than absolute cap but expires_at in future -> GET /today", r.status_code, "(200 = cap enforced only via touch clamp, see note)")
say("expires_at after touch:", db_exec(db, "SELECT expires_at FROM sessions WHERE created_at='2020-01-01T00:00:00.000000Z'"))
