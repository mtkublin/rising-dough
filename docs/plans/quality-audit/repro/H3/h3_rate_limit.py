"""H3: rate-limit bypass attempts against the real ASGI stack under uvicorn on 127.0.0.1.

uvicorn is started exactly as the Dockerfile does (--proxy-headers --forwarded-allow-ips=*), so
X-Forwarded-For is honoured. Parallel bursts are capped at 20 requests (rules of engagement).

R1 parallel TOCTOU on the per-minute counter     R2 case/whitespace email variants
R3 X-Forwarded-For rotation                      R4 XFF multi-value / arbitrary-string identity
R5 victim bucket poisoning via spoofed XFF       R6 audit growth for throttled attempts
R7 step-up (reauth) bucket exhaustion by a session thief

Run: uv run python docs/plans/quality-audit/repro/H3/h3_rate_limit.py
"""

from __future__ import annotations

import re
import socket
import sys
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import uvicorn

sys.path.insert(0, str(Path(__file__).parent))
from _common import PW, SESSION, client, db_exec, hdr, login, make_app, new_db, say  # noqa: E402

db = new_db("rate")
app, settings = make_app(db)  # DEFAULT limits: 5/min + 20/h per ip+email, 100/h per ip

with socket.socket() as s:
    s.bind(("127.0.0.1", 0))
    PORT = s.getsockname()[1]
server = uvicorn.Server(
    uvicorn.Config(app, host="127.0.0.1", port=PORT, proxy_headers=True, forwarded_allow_ips="*", log_level="error")
)
threading.Thread(target=server.run, daemon=True).start()
while not server.started:
    time.sleep(0.05)
BASE = f"http://127.0.0.1:{PORT}"


def attempt(email: str, password: str = "wrong-password-0000", xff: str | None = None) -> int:
    h = {}
    if xff:
        h["X-Forwarded-For"] = xff
    with httpx.Client(base_url=BASE, headers=h) as c:
        g = c.get("/auth/login")
        tok = re.search(r"__Host-csrf=([^;]+)", g.headers.get("set-cookie", "")).group(1)
        r = c.post("/auth/login", data={"email": email, "password": password, "_csrf_token": tok},
                   headers={"Cookie": f"__Host-csrf={tok}"})
        return r.status_code


def keys(like: str = "login:%") -> list[str]:
    return [r[0] for r in db_exec(db, "SELECT key FROM auth_rate_limit WHERE key LIKE ? ORDER BY key", (like,))]


def reset():
    db_exec(db, "DELETE FROM auth_rate_limit")
    db_exec(db, "DELETE FROM audit_log WHERE entity_type='auth_event'")


say("== R1 20 parallel wrong-password logins, one ip+email, default limit 5/min")
reset()
with ThreadPoolExecutor(20) as ex:
    res = list(ex.map(lambda _: attempt("v@x.test"), range(20)))
say("status histogram:", dict(Counter(res)), "(exactly 5 x 401 expected if no TOCTOU)")
say("counter rows:", db_exec(db, "SELECT key, count FROM auth_rate_limit WHERE key LIKE 'login:60s:%'"))

say("\n== R2 case / whitespace email variants share one counter")
reset()
variants = ["v@x.test", "V@X.TEST", " v@x.test", "v@x.test ", "\tV@x.test\n", "v@X.test", "V@x.test"]
res = [attempt(v, xff="10.9.9.9") for v in variants]
say("statuses for 7 variants from one IP:", res, "(429 from the 6th = shared)")
say("distinct counter keys:", len(keys("login:60s:%")))

say("\n== R3 X-Forwarded-For rotation: 30 wrong passwords against one account, then the right one")
reset()
res = [attempt("v@x.test", xff=f"10.1.{i // 250}.{i % 250 + 1}") for i in range(30)]
say("statuses for 30 attempts with rotating XFF:", dict(Counter(res)), "(no 429 = per-account limit absent)")
say("then correct password from a 31st address ->", attempt("v@x.test", PW, xff="10.1.9.9"))
say("same without XFF rotation (fixed XFF, 8 attempts) ->", [attempt("v@x.test", xff="10.2.2.2") for _ in range(8)])
say("counter rows (login scope) after R3:", len(keys("login:60s:%")))

say("\n== R4 which XFF entry is used / is the value validated?")
reset()
attempt("v@x.test", xff="203.0.113.50, 198.51.100.1")
attempt("v@x.test", xff="not-an-ip")
attempt("v@x.test", xff="1.2.3.4|email=victim@x.test")
attempt("v@x.test")
for k in keys("login:60s:%"):
    say("  key:", k)

say("\n== R5 poison the victim's bucket from the attacker's own address by spoofing the victim's IP")
reset()
VICTIM_IP = "203.0.113.77"
for _ in range(6):
    attempt("v@x.test", xff=VICTIM_IP)  # attacker, 6 wrong attempts labelled as the victim's IP
say("victim from the real address with the RIGHT password ->", attempt("v@x.test", PW, xff=VICTIM_IP), "(429 = locked out)")
say("victim from another address ->", attempt("v@x.test", PW, xff="198.51.100.9"))

say("\n== R6 audit-log growth: every throttled attempt still writes an audit row")
reset()
for _ in range(15):
    attempt("v@x.test", xff="10.7.7.7")
n = db_exec(db, "SELECT count(*) FROM audit_log WHERE entity_type='auth_event'")[0][0]
say("auth_event audit rows after 15 attempts from one source (5 allowed + 10 throttled):", n)

say("\n== R8 unvalidated XFF value is stored as the session ip and shown on the Security page")
reset()
payload = '<img src=x onerror=alert(1)>"\'&'
with httpx.Client(base_url=BASE, headers={"X-Forwarded-For": payload}) as c:
    g = c.get("/auth/login")
    tok = re.search(r"__Host-csrf=([^;]+)", g.headers.get("set-cookie", "")).group(1)
    r = c.post("/auth/login", data={"email": "v@x.test", "password": PW, "_csrf_token": tok}, headers={"Cookie": f"__Host-csrf={tok}"})
    sess = re.search(r"__Host-session=([^;]+)", r.headers.get("set-cookie", "")).group(1)
    say("login with XFF payload ->", r.status_code)
    say("sessions.ip stored:", db_exec(db, "SELECT ip FROM sessions ORDER BY rowid DESC LIMIT 1"))
    page = c.get("/settings/security", headers={"Cookie": f"__Host-session={sess}; __Host-csrf={tok}"})
    say("GET /settings/security ->", page.status_code, "| raw payload in HTML:", "<img src=x onerror" in page.text, "| escaped form present:", "&lt;img src=x onerror" in page.text)
    ips = db_exec(db, "SELECT ip FROM audit_log WHERE ip LIKE '%onerror%' LIMIT 1")
    say("audit_log.ip stored raw:", ips)

server.should_exit = True

say("\n== R7 session thief exhausts the victim's per-user step-up bucket")
db2 = new_db("rate2")
app2, _ = make_app(db2)
v = client(app2)
login(v)
thief = client(app2)
thief.cookies.set(SESSION, [c.value for c in v.cookies.jar if c.name == SESSION][-1], domain="testserver.local")
thief.get("/auth/login")
codes = []
for _ in range(6):
    r = thief.post("/auth/reauth", data={"password": "bad-password-xxxxx", "next": "/", "_csrf_token": thief.cookies.get("__Host-csrf")})
    codes.append(r.status_code)
say("thief wrong reauth attempts:", codes)
r = v.post("/auth/reauth", data={"password": PW, "next": "/", "_csrf_token": v.cookies.get("__Host-csrf")})
say("legit owner reauth with the right password right after ->", r.status_code, "(429 = step-up blocked for the owner for the window)")
